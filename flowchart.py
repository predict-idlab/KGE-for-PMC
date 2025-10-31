from classes import *

nodes = {}
decisions = {}
connectors = {}


def parse_fc(fcfile):
    with open(fcfile) as fcin:
        substitutions, bindings, creations = {}, {}, defaultdict(list)
        current_module, module_index = None, defaultdict(int)
        modules = {}
        for line in fcin:
            split = line.strip().split(" ")
            if "-->" in line:
                if "{" in split[0]:
                    source = split[0].split("{")[0]
                    sbinding = split[0].split("{")[1][:-2]
                else:
                    source = split[0].split("[")[0]
                    sbinding = split[0].split("[")[1][:-1]
                rel = split[1].split("--")[1]
                if "{" in split[2]:
                    target = split[2].split("{")[0]
                    tbinding = split[2].split("{")[1][:-2]
                else:
                    target = split[2].split("[")[0]
                    tbinding = split[2].split("[")[1][:-1]
                creations[source].append(rel + ":" + target)
                substitutions[source] = sbinding
                substitutions[target] = tbinding
                if source not in modules:
                    modules[source] = (current_module, module_index[current_module])
                    module_index[current_module] += 1
            elif split[0] == "class":
                bindings[split[1]] = split[2]
            elif split[0] == "subgraph":
                current_module = split[1]
            elif split[0] == "end":
                current_module = None
        return substitutions, bindings, creations, modules
