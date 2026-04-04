# sprinkler_system.py
class SprinklerSystem:
    def __init__(self):
        self.nodes = []
        self.pipes = []
        self.sprinklers = []
        self.fittings = []
        self.supply_node = None   # WaterSupply instance (set by Model_Space)

    def add_node(self, node):
        self.nodes.append(node)
        return node

    def add_pipe(self, pipe):
        self.pipes.append(pipe)
        return pipe

    def add_sprinkler(self, sprinkler):
        self.sprinklers.append(sprinkler)
        return sprinkler

    def add_fitting(self, fitting):
        self.fittings.append(fitting)
        return fitting

    def remove_node(self, node):
        if node in self.nodes:
            self.nodes.remove(node)

    def remove_pipe(self, pipe):
        if pipe in self.pipes:
            self.pipes.remove(pipe)

    def remove_sprinkler(self, sprinkler):
        if sprinkler in self.sprinklers:
            self.sprinklers.remove(sprinkler)

    def remove_fitting(self, fitting):
        if fitting in self.fittings:
            self.fittings.remove(fitting)

    def report(self):
        return {
            "nodes": len(self.nodes),
            "pipes": len(self.pipes),
            "sprinklers": len(self.sprinklers),
            "fittings": len(self.fittings),
        }
