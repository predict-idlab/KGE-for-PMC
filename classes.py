import json


def parse_cc(ccfile):
    with open(ccfile) as ccin:
        substitutions, bindings, creations = {}, {}, {}
        current_module, module_index = None, 0
        modules = {}
        for line in ccin:
            split = line.strip().split(" ")
            if split[0] == "@bind":
                ssplit = split[1].split(":")
                substitutions[ssplit[0]] = ssplit[2]
                bindings[ssplit[0]] = ssplit[1]
            elif split[0] == "@create":
                creations[split[1]] = split[2:]
                modules[split[1]] = (current_module, module_index)
                module_index += 1
            elif split[0] == "@begin":
                current_module = split[1]
                module_index = 0
            elif split[0] == "@end":
                current_module = None
        return substitutions, bindings, creations, modules


def parse_classes(shfile, cfile):
    templates = {}
    with open(shfile) as shin:
        shdict = json.load(shin)
        print("shapes:", shdict)
        graph = shdict["@graph"]
        shcontext = shdict["@context"]
        for entry in graph:
            # store entire entry
            print(entry)
            templates[entry['targetClass']['@id'].split(":")[-1]] = entry

    classes = {}
    with open(cfile) as cin:
        cdict = json.load(cin)
        print("classes:", cdict)
        graph = cdict["@graph"]
        ccontext = cdict["@context"]
        for entry in graph:
            # store entire entry
            classes[entry['@id'].split(":")[-1]] = entry
    return templates, classes, shcontext, ccontext
