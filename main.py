import rdflib
from copy import deepcopy
from dotted.collection import DottedDict
from collections import defaultdict

from flowchart import *


def jsonld_to_rdf(filename):
    graph = rdflib.Graph()
    graph.parse(filename, format="json-ld")
    graph.serialize(filename.split(".")[0] + ".owl", format="pretty-xml")


def jsonld_to_ttl(filename):
    graph = rdflib.Graph()
    graph.parse(filename, format="json-ld")
    graph.serialize(filename.split(".")[0] + ".ttl", format="turtle")


def create_classes(shfile, cfile, fcfile, to_file=False):
    substitutions, bindings, creations, modules = parse_fc(fcfile)
    templates, classes, shcontext, ccontext = parse_classes(shfile, cfile)

    print("SUBSTITUTIONS:", substitutions)
    print("BINDINGS:", bindings)
    print("CREATIONS:", creations)
    print("MODULES:", modules)
    print("TEMPLATES:", templates)
    print("CLASSES:", classes)

    crea_rels = set()
    for key, val in creations.items():
        for scheme in val:
            crea_rels.add(scheme.split(':')[0])
    print("Get all relationships that are involved in substitutions:", crea_rels)

    def unfurl_ts(t, binding, nested_templates={}, classes_so_far=set()):
        if 'property' in t:
            for i, path in enumerate(t['property']):
                if 'class' in path:
                    nested_templates[binding + "." + path['name']] = (
                    'property.' + str(i) + '.class', path['class']['@id'])
            for path in t['property']:
                if 'class' in path:
                    nt_binding = path['class']['@id'].split(":")[-1]
                    # avoid endless recurrence during unfurling...
                    if nt_binding not in classes_so_far and nt_binding != 'PMCModule':
                        # make sure not to unfurl when relationships are not auxiliary
                        if 'name' in path and path['name'] not in crea_rels:
                            print('Recursion into', nt_binding, path)
                            classes_so_far.add(nt_binding)
                            nested_templates = unfurl_ts(templates[nt_binding], nt_binding, nested_templates,
                                                         classes_so_far)
        else:
            return nested_templates
        return nested_templates

    def get_extras(t):
        if 'property' in t:
            for i, path in enumerate(t['property']):
                if 'in' in path:
                    return path['in']['@list']

    def perform_top_level_substitution(t, s):
        # convert to dotted dict for efficient indexing
        t = DottedDict(t)

        # substitute the top-level names
        t['@id'] = t['@id'].replace("PMC", s)
        t['targetClass']['@id'] = t['targetClass']['@id'].replace("PMC", s)
        return t

    def perform_primary_substitution(cid):
        print("\n\n Performing primary substitution...", cid)
        binding = bindings[cid]
        template = templates[binding]
        subst = substitutions[cid]
        print(binding, template, subst)

        # perform substitutions
        ts = {}
        nt = unfurl_ts(template, binding, nested_templates={}, classes_so_far=set())
        print(nt)
        for key in nt:
            print(key)
            tid, name = key.split(".")
            # first perform top-level substitution
            t = templates[tid]
            if tid in ts:
                t = ts[tid]
            new_t = perform_top_level_substitution(t, subst)
            print("\n top-level substitution:", subst, new_t, "\n\n")
            # then perform nested substitution
            new_t[nt[key][0]]['@id'] = new_t[nt[key][0]]['@id'].replace("PMC", subst)
            # apply nested substitutions
            ts[tid] = new_t

        print("\n primary substitution finished:", cid, ts, "\n\n")

        return ts

    def perform_secondary_substitution(cid, ts):
        print("Performing secondary substitution...", cid)
        binding = bindings[cid]
        template = templates[binding]
        subst = substitutions[cid]

        new_classes, new_templates = [], []

        # substitute nested classes according to creation schema
        nt = unfurl_ts(template, binding, nested_templates={}, classes_so_far=set())
        frequencies = defaultdict(int)
        for c in creations[cid]:
            tname, ttid = c.split(":")
            frequencies[tname] += 1
            print("Creating", cid, "rule:", tname, ":", ttid)
            # get keys relevant to creation formula
            keys = [key for key in nt.keys() if tname in key]
            for key in keys:
                tid, name = key.split(".")
                # perform substitution according to creation schema
                new_class = 'pmc:' + bindings[ttid].replace('PMC', substitutions[ttid])
                print("new class to be substituted:", new_class, "using key", key)
                # more than one rule for the same property
                if frequencies[tname] > 1:
                    split_key = nt[key][0].split(".")
                    # deep copy to prevent multiple new entries from being overwritten simultaneously
                    ts_cp = DottedDict(deepcopy(ts[tid].to_python()))
                    new_entry = ts_cp[split_key[0] + "." + split_key[1]]
                    new_entry['class']['@id'] = new_class
                    ts[tid][split_key[0]].append(new_entry)
                else:
                    # just replace
                    ts[tid][nt[key][0]]['@id'] = new_class
                    print(ts[tid])

                # new class and corresponding superclass
                new_classes.append((new_class, 'pmc:' + bindings[ttid]))

        # get remaining new classes & new templates
        for tid in ts:
            # new class and corresponding superclass
            new_classes.append((ts[tid]['targetClass']['@id'], 'pmc:' + tid))
            # new template in pythonic form
            new_templates.append(ts[tid].to_python())
        return new_classes, new_templates

    shgraph = {'@context': shcontext, '@graph': []}
    cgraph = {'@context': ccontext, '@graph': []}
    # create new templates
    already_created_classes = set()
    for cid in creations:
        new_ts = perform_primary_substitution(cid)
        new_cs, new_ts = perform_secondary_substitution(cid, new_ts)
        for new_t in new_ts:
            # only for top-level template...
            if new_t['targetClass']['@id'] == "pmc:" + bindings[cid].replace("PMC", substitutions[cid]):
                module, module_index = modules[cid]
                # check if module linking is required
                module_rels = module.split('.')
                if len(module_rels) > 2:
                    module_name = module_rels[0]
                    to_from_rel = module_rels[2]
                    # add module link
                    new_t['property'].append(
                        {'path': {'@id': 'pmc:' + to_from_rel}, 'name': 'containedIn', 'minCount': 1, 'maxCount': 1,
                         'class': {'@id': 'pmc:' + module_name + 'Module'}})
                    print('Add is-contained-in relationship:', new_t)
            shgraph['@graph'].append(new_t)
        # also create new classes
        for (new_c, old_c) in new_cs:
            if new_c not in already_created_classes:
                c_entry = {'@id': new_c, '@type': 'Class', 'subClassOf': {'@list': [{'@id': 'pmc:' + old_c}]}}
                cgraph['@graph'].append(c_entry)
                already_created_classes.add(new_c)
        # also create extra classes
        for new_t in new_ts:
            extra_classes = get_extras(new_t)
            if extra_classes is not None:
                for extra_class in extra_classes:
                    ec = extra_class['@id']
                    if 'pmc' in ec:
                        ec_new = ec.replace('PMC', substitutions[cid])
                        if ec_new not in already_created_classes:
                            print("Creating extra class:", ec_new)
                            c_entry = {'@id': ec_new, '@type': 'Class', 'subClassOf': {'@list': [{'@id': ec}]}}
                            cgraph['@graph'].append(c_entry)
                            already_created_classes.add(ec_new)

    print("Created shapes graph:", shgraph)
    print("Created classes graph:", cgraph)

    # create modules
    new_modules, max_idx_per_module = {}, defaultdict(int)
    for cid in modules:
        if modules[cid][0] is None:
            continue
        print("Creating module...", cid, modules[cid])
        # determine class name for current step
        new_class = "pmc:" + bindings[cid].replace("PMC", substitutions[cid])
        # get module to which current step belongs
        module, module_index = modules[cid]
        module_name = module
        # check if module creation requires container statements
        module_rels = module.split('.')
        if len(module_rels) > 1:
            module_name = module_rels[0]
            from_to_rel = module_rels[1]
        print("Parsed module", module_name, from_to_rel)
        if module_index == 0:  # beginning of module
            # get module shape
            new_t = templates['PMCModule']
            new_t = perform_top_level_substitution(new_t, module_name)
            # get easy-access indexes for each property
            nt = unfurl_ts(new_t, 'PMCModule', nested_templates={}, classes_so_far=set())
            # put current step where it belongs inside the module
            new_t[nt['PMCModule.begin'][0]] = new_class
            # add container relationships
            if from_to_rel is not None:
                new_t[nt['PMCModule.' + from_to_rel][0]] = [new_class]
                print("Add contains relationship...", new_t)
            new_modules[module_name] = new_t, nt
        else:  # somewhere inside module
            new_t, nt = new_modules[module_name]
            # add container relationships
            if from_to_rel is not None:
                new_t[nt['PMCModule.' + from_to_rel][0]].append(new_class)
                print("Add contains relationship...", new_t)
            # update the end, as we get closer to the end of the module
            if module_index > max_idx_per_module[module_name]:
                new_t[nt['PMCModule.end'][0]] = new_class
                new_modules[module_name] = new_t, nt
                max_idx_per_module[module_name] = max(module_index, max_idx_per_module[module_name])

    # add modules to templates and classes
    new_modules = [m[0].to_python() for m in new_modules.values()]
    for module in new_modules:
        shgraph['@graph'].append(module)
        c_entry = {'@id': module['targetClass']['@id'], '@type': 'Class',
                   'subClassOf': {'@list': [{'@id': 'pmc:PMCModule'}]}}
        cgraph['@graph'].append(c_entry)

    print("Shapes graph with modules:", shgraph)
    print("Classes graph with modules:", cgraph)

    if to_file:
        print("Writing shapes to file...")
        with open("KGs/ExampleShapes.jsonld", 'w') as shout:
            obj = json.dumps(shgraph)
            shout.write(obj)

        print("Writing classes to file...")
        with open("KGs/ExampleClasses.jsonld", 'w') as cout:
            obj = json.dumps(cgraph)
            cout.write(obj)


create_classes("KGs/PMCShapes.jsonld", "KGs/PMCClasses.jsonld", "merweb-diagrams/example_pmc_diagram.txt", to_file=True)
jsonld_to_ttl("KGs/ExampleShapes.jsonld")
jsonld_to_ttl("KGs/ExampleClasses.jsonld")
