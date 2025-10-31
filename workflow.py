import rdflib
from rdflib.extras.external_graph_libs import rdflib_to_networkx_multidigraph
import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict


base_uri = "https://pmc/classes/"


class Step:
    """
    A step in a workflow.
    """
    def __init__(self, name, triples):
        self.name = name
        self.triples = triples
        self.next_steps = defaultdict(list)
        self.auxiliary_classes = defaultdict(dict)

        self.value = None

        self.instances = []


class Module:
    """
    A module in a workflow.
    """
    def __init__(self, name, triples, begin=None, end=None):
        self.name = name
        self.triples = triples
        self.begin, self.end = begin, end


class KGAsWorkflow:
    """
    A view of a KG as a workflow.
    """

    def __init__(self, rootURI):
        self.shapes = None

        self.modules = {}
        self.steps = {}

        self.first = None
        self.rootURI = rootURI

        self.classes_to_shapes = {}
        self.shapes_to_classes = {}
        self.instances_per_class = defaultdict(list)

    def init(self, start=None):
        self.__init_iterator(start)

    def __init_iterator(self, start=None):
        self.explored = []

        if start:
            self.queue = [start]
            self.visited = [start]
        else:
            self.queue = [self.first]
            self.visited = [self.first]

    def next(self, reset=False, with_subseq=False, verbose=False):
        """
        Go to next step in workflow.
        :param reset: reset the iterator before going to the next step
        :param with_subseq: also return subsequent steps
        :param verbose: toggle iterator verbosity
        :return:
        """
        if reset:
            self.__init_iterator()

        # get next from front of queue
        if len(self.queue) > 0:
            current_step = self.queue.pop(0)
            self.explored.append(current_step)

            if verbose:
                print("Current step:", current_step.name)
                print("###############################")
                print("Next steps:")
                for rel in current_step.next_steps:
                    print("Via", rel, "to", [s.name for s in current_step.next_steps[rel]])
                print("-------------------------------")
                print("Triples for", current_step.name)
                for s, p, o in current_step.triples:
                    print(s, p, o)
                print("-------------------------------")
                print("-------------------------------")
                print("Instantiated?", len(current_step.instances) > 0)
                if len(current_step.instances) > 0:
                    for instance in current_step.instances:
                        print("Next steps for instance", instance.name)
                        for rel in instance.next_steps:
                            print("Via", rel, "to", [s.name for s in instance.next_steps[rel]])
                        print("-------------------------------")
                        print("Auxiliary instantiations:")
                        for s, p, o in instance.triples:
                            print(s, p, o)
                        print("-------------------------------")
                        print("-------------------------------")
                print("###############################\n\n")

            # add neighbours
            subsequent = []
            for next_rel in current_step.next_steps:
                next_steps = current_step.next_steps[next_rel]
                for next_step in next_steps:
                    if next_step not in self.visited:
                        self.queue.append(next_step)
                        self.visited.append(next_step)
                        subsequent.append((next_rel, self.queue[-1]))

            if with_subseq:
                return current_step, subsequent
            return current_step

        if with_subseq:
            return None, None
        return None

    def look_for_instance_depth_first(self, start, excluding={}):
        """
        Look for instance in the subtree starting from a given step.

        :param start: start from here
        :param excluding: skip these steps
        """

        if start.instance and start not in excluding:
            return start
        else:
            for step in start.next_steps:
                found = self.look_for_instance_depth_first(step)
                if found and found not in excluding:
                    return found
            return None

    def instantiate(self, step_name, with_literal={}):
        """
        Instantiate a step in the workflow.
        :param step_name: name of the step to be instantiated
        :param with_literal: dictionary indicating the values that need to be associated with specific relationships
        """
        # assume that literal info is a dictionary
        abox = rdflib.Graph()
        to_be_added = []

        name = rdflib.term.URIRef(self.shapes_to_classes[step_name] + "_ind_" + str(len(self.instances_per_class[self.shapes_to_classes[step_name]])))
        self.steps[step_name].instances.append(Step(name, None))

        for aux_class in self.steps[step_name].auxiliary_classes:
            # instantiate the classes
            if '#' in str(aux_class):
                new_s = str(aux_class).split("#")[-1]
            else:
                new_s = str(aux_class).split("/")[-1]
            s, p, o = (rdflib.term.URIRef(base_uri + new_s + "_ind_" + str(len(self.instances_per_class[aux_class]))),
                       rdflib.term.URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
                       aux_class)
            abox.add((s, p, o))
            if (o, s) not in to_be_added:  # avoid duplicates
                to_be_added.append((o, s))
            # instantiate the relationships
            for rel in self.steps[step_name].auxiliary_classes[aux_class]:
                rel_class = self.steps[step_name].auxiliary_classes[aux_class][rel][0]
                if '#' in str(rel_class):
                    new_rel_ind = str(rel_class).split("#")[-1]
                else:
                    new_rel_ind = str(rel_class).split("/")[-1]
                rel_ind = rdflib.term.URIRef(
                    base_uri + new_rel_ind + "_ind_" + str(len(self.instances_per_class[rel_class])))
                if rel_class == rdflib.term.URIRef('rdfs:Literal') and rel in with_literal:
                    abox.add((s, rel, rdflib.term.Literal(with_literal[rel])))
                    self.steps[step_name].instances[-1].value = with_literal[rel]
                else:  # new individual is not a literal
                    # add type declaration for the new individual
                    abox.add((rel_ind,
                              rdflib.term.URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
                              rel_class))
                    if (rel_class, rel_ind) not in to_be_added:  # avoid duplicates
                        to_be_added.append((rel_class, rel_ind))
                    # add relation between subject and the new individual
                    abox.add((s, rel, rel_ind))

        for c, i in to_be_added:
            self.instances_per_class[c].append(i)

        # in case the root class was not added as part of the auxiliary classes
        if self.shapes_to_classes[step_name] not in self.instances_per_class or len(self.instances_per_class[self.shapes_to_classes[step_name]]) == 0:
            s, p, o = (rdflib.term.URIRef(name),
                       rdflib.term.URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
                       self.shapes_to_classes[step_name])
            abox.add((s, p, o))
        self.steps[step_name].instances[-1].triples = abox

        return self.steps[step_name].instances[-1]

    def visualize(self):
        G = rdflib_to_networkx_multidigraph(self.to_triples())

        # Plot Networkx instance of RDF Graph
        pos = nx.spring_layout(G, scale=2)
        edge_labels = nx.get_edge_attributes(G, 'r')
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
        nx.draw(G, with_labels=True)
        plt.savefig('graph.png', dpi=300, bbox_inches='tight')
        plt.show()

    def to_triples(self):
        """
        Convert the workflow to a triple store.
        """
        store = rdflib.Graph()
        for step in self.steps:
            store += self.steps[step].triples
        for module in self.modules:
            store += self.modules[module].triples
        return store

    def from_shapes(self, shapes):
        """
        Create a workflow based on a triple store containing shapes.
        :param shapes: a triple store containing shapes
        """
        print("Building graph from shapes...")
        self.shapes = shapes
        triples_per_entity = {}

        for subj in shapes.subjects(predicate=None, object=None):
            triples_per_entity[subj] = list(shapes.triples((subj, None, None)))
        # for obj in shapes.objects(subject=None, predicate=None):
        #     triples_per_entity[obj] = list(shapes.triples((None, None, obj)))

        to_delete = []
        auxiliary_classes = defaultdict(list)
        # gather all steps and modules
        for subj in triples_per_entity:
            if type(subj) == rdflib.term.URIRef:
                if 'Step' in subj or 'Module' in subj:
                    for obj in shapes.objects(subject=subj, predicate=None):
                        if obj in triples_per_entity:
                            triples_per_entity[subj].extend(triples_per_entity[obj])
                else:
                    to_delete.append(subj)
                    auxiliary_classes[subj].extend(triples_per_entity[subj])
                    for obj in shapes.objects(subject=subj, predicate=None):
                        if obj in triples_per_entity:
                            auxiliary_classes[subj].extend(triples_per_entity[obj])
            else:
                to_delete.append(subj)

        # separate them
        triples_per_step = {}
        triples_per_module = {}
        for subj in triples_per_entity:
            if subj not in to_delete:
                if 'Step' in subj:
                    triples_per_step[subj] = triples_per_entity[subj]
                elif 'Module' in subj:
                    triples_per_module[subj] = triples_per_entity[subj]

        # create an auxiliary kg to query from
        auxiliary_kg = rdflib.Graph()
        for tr_list in auxiliary_classes.values():
            for tr in tr_list:
                auxiliary_kg.add(tr)

        # gather all relevant triples per shape
        for step in triples_per_step:
            # print("Step:", step)
            kg = rdflib.Graph()
            for tr in triples_per_step[step]:
                kg.add(tr)
            triples_per_step[step] = kg
            step_obj = Step(step, kg)

            flow_paths = {rdflib.term.URIRef('https://pmc/classes/followedBy'),
                          rdflib.term.URIRef('http://www.daml.org/services/owl-s/1.1/Process.owl#then'),
                          rdflib.term.URIRef('http://www.daml.org/services/owl-s/1.1/Process.owl#else')}

            # create step object per step shape
            properties = list(
                kg.objects(subject=step, predicate=rdflib.term.URIRef('http://www.w3.org/ns/shacl#property')))
            for prop in properties:
                for path in kg.objects(subject=prop, predicate=rdflib.term.URIRef('http://www.w3.org/ns/shacl#path')):
                    step_classes = list(kg.objects(subject=step, predicate=rdflib.term.URIRef(
                        'http://www.w3.org/ns/shacl#targetClass')))
                    assert len(step_classes) <= 1
                    if len(step_classes) == 1:
                        self.classes_to_shapes[step_classes[0]] = step
                        self.shapes_to_classes[step] = step_classes[0]
                    linked_classes = list(
                        kg.objects(subject=prop, predicate=rdflib.term.URIRef('http://www.w3.org/ns/shacl#class')))
                    if path in flow_paths:
                        step_obj.next_steps[path].extend(linked_classes)
                    else:
                        # auxiliary classes are ordered per shape, per path
                        if path in step_obj.auxiliary_classes[self.shapes_to_classes[step]]:
                            step_obj.auxiliary_classes[self.shapes_to_classes[step]][path].extend(linked_classes)
                        else:
                            step_obj.auxiliary_classes[self.shapes_to_classes[step]][path] = linked_classes

            # find additional auxiliary classes for a given step
            def extend_aux(shape, path, old_entries):
                new_entries = defaultdict(dict)
                for aux_class in old_entries[shape][path]:
                    if aux_class not in self.classes_to_shapes:
                        aux_shapes = list(auxiliary_kg.subjects(
                            predicate=rdflib.term.URIRef('http://www.w3.org/ns/shacl#targetClass'), object=aux_class))
                        assert len(aux_shapes) <= 1
                        if len(aux_shapes) == 1:
                            self.classes_to_shapes[aux_class] = aux_shapes[0]
                            self.shapes_to_classes[aux_shapes[0]] = aux_class
                            # gather all relevant auxiliary classes (from the total pool of auxiliary classes)
                            aux_triples = auxiliary_classes[self.classes_to_shapes[aux_class]]
                            temp_kg = rdflib.Graph()
                            for tr in aux_triples:
                                temp_kg.add(tr)
                            # create new auxiliary entries
                            properties = list(temp_kg.objects(subject=self.classes_to_shapes[aux_class],
                                                              predicate=rdflib.term.URIRef(
                                                                  'http://www.w3.org/ns/shacl#property')))
                            for prop in properties:
                                for path in temp_kg.objects(subject=prop, predicate=rdflib.term.URIRef(
                                        'http://www.w3.org/ns/shacl#path')):
                                    linked_classes = list(temp_kg.objects(subject=prop, predicate=rdflib.term.URIRef(
                                        'http://www.w3.org/ns/shacl#class')))
                                    if path in new_entries[aux_class]:
                                        new_entries[aux_class][path].extend(linked_classes)
                                    else:
                                        new_entries[aux_class][path] = linked_classes

                return new_entries

            # further extend the auxiliary classes
            while True:
                new_entries = defaultdict(dict)
                for shape in step_obj.auxiliary_classes:
                    for path in step_obj.auxiliary_classes[shape]:
                        # cumulate new auxiliary entries
                        new_entries = {**new_entries, **extend_aux(shape, path, step_obj.auxiliary_classes)}
                old_size = len(step_obj.auxiliary_classes)
                # update step object with new auxiliary entries
                step_obj.auxiliary_classes = {**new_entries, **step_obj.auxiliary_classes}
                new_size = len(step_obj.auxiliary_classes)
                if new_size <= old_size:
                    break

            self.steps[step_obj.name] = step_obj

        # fix step linking:
        print(self.classes_to_shapes)
        for step in self.steps:
            for path in self.steps[step].next_steps:
                new_nsteps = []
                for nstep in self.steps[step].next_steps[path]:
                    if nstep not in self.classes_to_shapes:
                        print("Not found:", nstep)
                        continue
                    name = self.classes_to_shapes[nstep]
                    actual_nstep = self.steps[name]
                    new_nsteps.append(actual_nstep)
                self.steps[step].next_steps[path] = new_nsteps

        # create module object per module
        self.first = self.steps[self.rootURI]
        for module in triples_per_module:
            kg = rdflib.Graph()
            for tr in triples_per_module[module]:
                kg.add(tr)
            triples_per_step[module] = kg
            module_obj = Module(module, kg)

            begin_path, end_path = rdflib.term.URIRef('https://pmc/classes/begin'), \
                                   rdflib.term.URIRef('https://pmc/classes/end')
            properties = list(
                kg.objects(subject=module, predicate=rdflib.term.URIRef('http://www.w3.org/ns/shacl#property')))
            for prop in properties:
                for path in kg.objects(subject=prop, predicate=rdflib.term.URIRef('http://www.w3.org/ns/shacl#path')):
                    linked_classes = list(
                        kg.objects(subject=prop, predicate=rdflib.term.URIRef('http://www.w3.org/ns/shacl#class')))
                    assert len(linked_classes) == 1
                    if path == begin_path:
                        module_obj.begin = linked_classes[0]
                    elif path == end_path:
                        module_obj.end = linked_classes[0]
            self.modules[module_obj.name] = module_obj