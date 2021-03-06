import copy

import networkx as nx
from collections import deque

__all__ = ["DisconnectivityGraph", "database2graph"]

def database2graph(database):
    """create a networkx graph from a pygmin database"""
    from pygmin.landscape import TSGraph # this must be imported here to avoid circular imports
    graph_wrapper = TSGraph(database)
    return graph_wrapper.graph
    

class Tree(object):
    """
    a Tree graph
    
    Each member of this class is a node in a Tree.  The node can
    have many children, but only one parent.  If the node has no
    parents then it is the root node.  If the node has no children
    then it is a leaf.
    """
    def __init__(self, parent=None):
        self.subtrees = []
        self.data = {}
        self.parent = parent
    
    def add_branch(self, branch):
        """make branch a child of this tree""" 
        self.subtrees.append(branch)
        branch.parent = self
    
    def make_branch(self):
        """return a new Tree which is a child of this Tree"""
        newtree = self.__class__(parent=self)
        self.subtrees.append(newtree)
        return newtree
    
    def get_subtrees(self):
        return self.get_branches()
    
    def get_branches(self):
        """return the list of branches of this tree"""
        return self.subtrees
    
    def number_of_branches(self):
        """return the number of branches of this tree"""
        return len(self.subtrees)
    
    def is_leaf(self):
        """return true if this tree has no descendents"""
        return self.number_of_branches() == 0
    
    def number_of_leaves(self):
        """return the number of leaves that are descendants of this Tree""" 
        if len(self.subtrees) == 0:
            nleaves = 1
        else:
            nleaves = 0
            for tree in self.subtrees:
                nleaves += tree.number_of_leaves()
        return nleaves
    
    def get_leaves(self):
        """return a list of the leaves that are descendants of this Tree""" 
        if self.is_leaf():
            leaves = [self]
        else:
            leaves = []
            for tree in self.subtrees:
                leaves += tree.get_leaves()
        return leaves
    
    def leaf_iterator(self):
        """iterate through the leaves that are descendants of this Tree""" 
        if self.is_leaf():
            yield self
        else:
            for tree in self.subtrees:
                for leaf in tree.leaf_iterator():
                    yield leaf
    
    def get_all_trees(self):
        """iterator over all subtrees, including self"""
        yield self
        for branch in self.get_branches():
            for subtree in branch.get_all_trees():
                yield subtree

class DGTree(Tree):
    """add a few functions to Tree to make it specific to disconnectivity graph"""
    def contains_minimum(self, min1):
        for leaf in self.get_leaves():
            if leaf.data["minimum"] == min1:
                return True
        return False
    
    def get_minima(self):
        return [leaf.data["minimum"] for leaf in self.get_leaves()]
    
    def get_one_minimum(self):
        """return a single minimum that is in this tree"""
        key = "_random_minimum"
        if self.is_leaf():
            return self.data["minimum"]
        elif key in self.data:
            return self.data[key]
        else:
            m = self.get_branches()[0].get_one_minimum()
            self.data[key] = m
            return m
    
    def _test_tree(self):
        tset = set()
        for tree in self.get_all_trees():
            if tree in tset:
                print "tree is touched twice"
                return False
            tset.add(tree)
        return True
        
           

class _MakeTree(object):
    """class to Make the disconnectivity graph tree
    
    Parameters
    ----------
    minima : list of Minimum objects
        the minima to contain in the disconnectivity graph
    transition_states : list of TransitionState objects
        the transition states to contain in the disconnectivity graph
    energy_levels : list of floats
        the energy levels at which to split the graph
    get_energy : callable
        a function which returns the energy of a transition state.  You can 
        use this to redefine the `energy` of a transition state, e.g. for a 
        free energy disconnectivity graph.
        
    Notes
    -----
    This algorithm starts from a completely disconnected graph and adds
    transition states one at a time, starting from the lowest energy transition
    state.  Connectivity is determined solely through labeling minima based on
    which cluster it's in (labels are called colors).  If a new transition
    state connects two previously disconnected clusters, the clusters are
    joined to make one single cluster.  As the transition states are added
    (sorted in energy) the energy levels are reached one at a time.  At each
    level, the state of the connectivity of the graph is saved in tree graphs.  
    """
    def __init__(self, minima, transition_states, energy_levels, get_energy=None):
        self.minima = minima
        self.transition_states = transition_states
        self.energy_levels = energy_levels
        self._get_energy = get_energy
        
        self._equal_colors = set()
        self._minimum_to_color = dict()
        self._color_to_minima = dict() 
    
    def _color_minima_initialize(self, minima):
        """give a color to all the minima"""
        for c, m in enumerate(minima):
            self._color_to_minima[c] = set([m])
            self._minimum_to_color[m] = c

    def _recolor(self, cold, cnew):
        """color cold will  be change to be cnew"""
        mold = self._color_to_minima[cold]
        self._color_to_minima[cnew].update(mold)
        self._color_to_minima.pop(cold)
        for m in mold:
            self._minimum_to_color[m] = cnew
    
    def _set_colors_equal(self, c1, c2):
        """join two colors"""
        if c1 == c2: return
        # for convenience, recolor the smaller group
        mlist1 = self._color_to_minima[c1]
        mlist2 = self._color_to_minima[c2]
        if len(mlist2) > len(mlist1):
            self._recolor(c1, c2)
        else:
            self._recolor(c2, c1)
    
    def _add_edge(self, min1, min2):
        """add an edge between min1 and min2
        
        if min1 and min2 belong to different color groups, those groups
        will be set equal
        """
        c1 = self._minimum_to_color[min1]
        c2 = self._minimum_to_color[min2]
        if c1 != c2:
            self._set_colors_equal(c1, c2)

    def get_energy(self, ts):
        if self._get_energy is None:
            return ts.energy
        else:
            return self._get_energy(ts)

    def make_tree(self):
        """make the disconnectivity tree"""
        # make list of transition states sorted so that lower energies are to the right
        tslist = self.transition_states
        # remove duplicate entries and sort
        tslist = list(set(tslist))
        tslist.sort(key=lambda ts: -self.get_energy(ts))
        self.transition_states = tslist 

        # color minima with initial values
        self._color_minima_initialize(self.minima)

        # make a tree leaf for every minimum
        ethresh = self.energy_levels[0]
        trees = []
        for m in self.minima:
            leaf = DGTree()
            leaf.data["minimum"] = m 
            leaf.data["ilevel"] = 0 
            leaf.data["ethresh"] = ethresh 
#            self.minimum_to_leave[m] = leaf
            trees.append(leaf)
        
        # build the tree up starting at the lowest level
        for ilevel in range(len(self.energy_levels)):
            trees = self._do_next_level(ilevel, trees)

        # remove redundant linear parentage 
        for tree in trees:
            self._remove_linear_parantage(tree)
        
        # deal with any disconnected parts
        energy_levels = self.energy_levels
        if len(trees) == 1:
            self.tree = trees[0]
        else:
            self.tree = DGTree()
            for t in trees:
                self.tree.add_branch(t)
            self.tree.data["ilevel"] = len(energy_levels)-1
            de = energy_levels[-1] - energy_levels[-2]
            self.tree.data["ethresh"] = energy_levels[-1] + 1.*de
            self.tree.data["children_not_connected"] = True

        if False:
            res = self.tree._test_tree()
            print "tree test result", res

        return self.tree
    
    
    def _remove_linear_parantage(self, tree):
        """remove redundant linear parentage
        
        remove all trees which have a parent and only one child
        
        also, correctly set ethresh for the minima (leaves)
        """
        if tree.is_leaf():
            # this tree represents a minimum
            if tree.parent is not None:
                # correct ethresh for this minimum
                tree.data["ethresh"] = tree.parent.data["ethresh"]
            return
        if tree.number_of_branches() == 1:
            # this tree has only one child.  remove it by bypassing it
            if tree.parent is not None:
                for branch in tree.get_subtrees():
                    tree.parent.add_branch(branch)
                tree.parent.subtrees.remove(tree)
        # deal with subtrees recursively
        # copy the list of subrees so the
        # list iterator doesn't get messed up if when the list is changed
        branches = copy.copy(tree.get_subtrees()) 
        for branch in branches:
            self._remove_linear_parantage(branch)
        
        
            
        
    def _do_next_level(self, ilevel, previous_trees):
        """do the disconnectivity analysis for energy level ilevel
        """
        ethresh = self.energy_levels[ilevel]
        
        # add the edges to the graph up to ethresh
        tslist = self.transition_states
        while len(tslist) > 0:
            ts = tslist[-1]
            if self.get_energy(ts) >= ethresh:
                break
            
            self._add_edge(ts.minimum1, ts.minimum2)
            
            # remove the transition state from the list
            tslist.pop()
        
        # make a new tree for every color (connected cluster)
        newtrees = []
        color_to_tree = dict()
        for c in self._color_to_minima.keys():
            newtree = DGTree()
            newtree.data["ilevel"] = ilevel 
            newtree.data["ethresh"] = ethresh
            newtrees.append(newtree)
            color_to_tree[c] = newtree
        
        # determine parentage
        for tree in previous_trees:
            m = tree.get_one_minimum()
            c = self._minimum_to_color[m]
            parent = color_to_tree[c]
            parent.add_branch(tree)
            
        return newtrees



class DisconnectivityGraph(object):
    """
    make a disconnectivity graph
    
    Parameters
    ----------
    graph : a networkx graph
        a graph with Minimum objects as nodes and transition
        states defining the edges.  You can use
        pygmin.landscape.TSGraph to create this from a database.
        
        >>> from pygmin.landscape import TSGraph
        >>> graphwrapper = TSGraph(database)
        >>> dg = DisconnectivityGraph(graphwrapper.graph)
         
    nlevels : int
        how many levels at which to bin the transition states
    Emax : float
        maximum energy for transition state cutoff.  Default
        is the maximum energy of all transition states.

    minima : list of Minima
        a list of minima to ensure are displayed in the graph.
        e.g. they will be displayed even if they're in a connected
        cluster smaller than smaller than subgraph_size
    subgraph_size : int
        if subgraph_size is not None then all disconnected graphs
        of size greater than subraph_size will be included.

    order_by_energy : bool
        order the subtrees by placing ones with lower energy closer
        to the center
    order_by_basin_size : bool
        order the subtrees by placing larger basins closer to the center
    center_gmin : bool
        when a node splits into its daughter
        nodes, the one containing the global minimum is always placed centrally
        (even if other nodes carry more minima). This does not guarantee that
        the global minimum is central in the overall diagram because other
        nodes may push the one containing the global minimum over to one side
    include_gmin : bool
        make sure to include the global minimum, even if it is not part of the
        main connected region
    node_offset : float
        offset between 0 and 1 for how to draw the angled lines.
        0 for no angle, draw horizontally out then vertically down.  1 for 
        angled lines all the way to the next energy level        
    energy_attribute : string, optional
        attribute which contains energy. default is energy. This attribute can
        be used to generate free energy disconnectivity graphs
    
    See Also
    ---------
    make_disconnectivity_graph.py :
        a script (in pygmin/scripts) to make the disconnectivity graph from the command line
    pygmin.storage.Database :
        The database format in which minima and transition states are stored in pygmin
    pygmin.landscape.TSGraph : 
        a wrapper to create a networkx Graph from a database
    
    Examples
    --------
    These examples assume a Database with minima already exists
    
    >>> from pygmin.landscape import TSGraph
    >>> import matplotlib.pyplot as plt
    >>> graphwrapper = TSGraph(database)
    >>> dg = DisconnectivityGraph(graphwrapper.graph)
    >>> dg.calculate()
    >>> dg.plot()
    >>> plt.show()

    """
    def __init__(self, graph, minima=None, nlevels=20, Emax=None,
                 subgraph_size=None, order_by_energy=False,
                 order_by_basin_size=True, node_offset=1.,
                 center_gmin=True, include_gmin=True, energy_attribute="energy"):
        self.graph = graph
        self.nlevels = nlevels
        self.Emax = Emax
        self.subgraph_size = subgraph_size
        self.order_by_basin_size = order_by_basin_size
        self.order_by_energy = order_by_energy
        self.center_gmin = center_gmin 
        self.gmin0 = None
        self.energy_attribute = energy_attribute
        self.node_offset = node_offset
        if self.center_gmin:
            include_gmin = True

        if minima is None:
            minima = []
        self.min0list = minima
        if include_gmin:
            #find the minimum energy node
            elist = [ (self._getEnergy(m), m) for m in self.graph.nodes() ]
            elist = sorted(elist)
            self.gmin0 = elist[0][1]
            self.min0list.append(self.gmin0)
#            print "min0", self.min0.energy, self.min0._id
        self.transition_states = nx.get_edge_attributes(self.graph, "ts")
        self.minimum_to_leave = dict()
        self.tree_list = [[] for x in range(self.nlevels)]

    def _getEnergy(self, node):
        """ get the energy of a node """
        return getattr(node, self.energy_attribute)
    
    def set_energy_levels(self, elevels):
        ''' manually set the energy levels '''
        self.elevels = elevels
        
    def _getTS(self, min1, min2):
        """return the transition state object between two minima"""
        try:
            return self.transition_states[(min1, min2)]
        except KeyError:
            return self.transition_states[(min2, min1)]


    #############################################################
    #functions for building the tree by splitting the graph into
    #connected components at each level 
    #############################################################


    def _connected_component_subgraphs(self, G):
        """
        redefine the networkx version because they use deepcopy
        on the nodes and edges
        
        this was copied and only slightly modified from the original
        source
        """
        cc=nx.connected_components(G)
        graph_list=[]
        for c in cc:
            graph_list.append(G.subgraph(c))
        return graph_list
    

    def _make_tree(self, graph, energy_levels):
        """make the disconnectivity graph tree
        """
        transition_states = nx.get_edge_attributes(graph, "ts").values()
        minima = graph.nodes()
        maketree = _MakeTree(minima, transition_states, energy_levels, 
                             get_energy=self._getEnergy)
        trees = maketree.make_tree()
        return trees
        
    ##########################################################
    #functions for determining the x position of the branches
    #and leaves
    ##########################################################
    
#    def _recursive_assign_id(self, tree):
#        subtrees = tree.get_subtrees()
#        for subtree in subtrees:
#            if subtree.number_of_branches() >= 2:
#                self.tree_list[subtree.data['ilevel']].append(subtree)
#
#                subtree.data['id'] = len(self.tree_list[subtree.data['ilevel']])
##                 print subtree.data.items()
##                 subtree.data['colour'] = tuple(np.random.random(3))
#            self._recursive_assign_id(subtree)
#
#            
#    def _assign_id(self, tree):
#        """
#        Determining the id of the branches and leaves
#        for selection purposes
#        """
#
#        self._recursive_assign_id(tree)
#        
#    def _set_colour(self,i,colour_dict):
#        '''
#        
#        '''
#        self.tree_list[i[0]][i[1]].data['colour'] = colour_dict[i]
#
#    def assign_colour(self, tree, colour):#colour_dict=[]):
#        '''
#        Colour trees according to `colour_dict`, a dictionay with 
#        (level, tree_index) tuples as keys and RGB colours as values
#        '''
##         for i in colour_dict: self._set_colour(i,colour_dict)
#        tree.data['colour'] = colour
##         print tree, tree.__dict__#.data.items()
##         print 'recursive'
#        self._recursive_colour_trees(tree, colour)
#            
#        
#    def _recursive_colour_trees(self, tree, colour):
#        '''
#        
#        '''
#        for s in tree.get_subtrees():
##             print tree, tree.__dict__
#            s.data['colour'] = colour #= s.parent.data['colour']
##             print s.parent.data['colour'], s.data['colour'], s.data['ilevel'], s.data['id']
#            self._recursive_colour_trees(s, colour)
            
            

    def _recursive_layout_x_axis(self, tree, xmin, dx_per_min):
#        nbranches = tree.number_of_branches()
        nminima = tree.number_of_leaves()
        subtrees = tree.get_subtrees()
        subtrees = self._order_trees(subtrees)
        tree.data["x"] = xmin + dx_per_min * nminima / 2.
        x = xmin
        for subtree in subtrees:
            self._recursive_layout_x_axis(subtree, x, dx_per_min)
            nminima_sub = subtree.number_of_leaves()
            x += dx_per_min * nminima_sub
  
    def _layout_x_axis(self, tree):
        """determining the x position of the branches and leaves
        
        used in displaying the disconnectivity graph
        """
        xmin = 4.0
        dx_per_min = 1
        self._recursive_layout_x_axis(tree, xmin, dx_per_min)

    def _tree_get_minimum_energy(self, tree, emin=1e100):
        """
        return the minimum energy of all the leaves in the tree
        """
        return min([leaf.data["minimum"].energy for leaf in tree.get_leaves()])

    def _order_trees(self, trees):
        """
        order a list of trees for printing
        
        This is the highest level function for ordering trees.  This, 
        and functions called by this, will account for all the user options 
        like center_gmin and order by energy
        """
        if self.order_by_energy:
            return self._order_trees_by_minimum_energy(trees)
        else:
            return self._order_trees_by_most_leaves(trees)

    def _order_trees_final(self, tree_value_list):
        """
        Parameters
        ----------
        tree_value_list :
            a list of (value, tree) pairs where value is the object
            by which to sort the trees
        
        Returns
        -------
        treelist :
            a list of trees ordered with the lowest in the center
            and the others placed successively on the left and right
        """
        mylist = sorted(tree_value_list)
        neworder = deque()
        for i in range(len(mylist)):
            if i % 2 == 0:
                neworder.append(mylist[i][1])
            else:
                neworder.appendleft(mylist[i][1])
        return list(neworder)

    def _ensure_gmin_is_center(self, tree_value_list):
        """ensure that the tree containing the global minimum has the lowest value
        """
        if self.gmin0 is None: return
        min0index = None
        for i in range(len(tree_value_list)):
            v, tree = tree_value_list[i]
            if self.gmin0 in [ leaf.data["minimum"] for leaf in tree.get_leaves()]:
                min0index = i
                break
        if min0index is not None:
            minvalue = min([v for v, tree in tree_value_list])
            #replace the value with a lower one
            #for the tree containing min0
            newvalue = minvalue - 1 #this won't work for non number values
            tree_value_list[i] = (newvalue, tree_value_list[i][1]) 
        return tree_value_list 

            
        

    def _order_trees_by_most_leaves(self, trees):
        """order list of trees by the number of leaves"""
#        if self.center_gmin:
#            return self._order_trees_by_most_leaves_and_global_min(trees)
        mylist = [ (tree.number_of_leaves(), tree) for tree in trees]
        if self.center_gmin:
            mylist = self._ensure_gmin_is_center(mylist)
        return self._order_trees_final(mylist)


    def _order_trees_by_minimum_energy(self, trees):
        """
        order trees with by the lowest energy minimum.  the global minimum
        goes in the center, with the remaining being placed alternating on the
        left and on the right.
        """
        mylist = [ (self._tree_get_minimum_energy(tree), tree) for tree in trees]
        return self._order_trees_final(mylist)
                        

    #######################################################################
    #functions which return the line segments that make up the visual graph
    #######################################################################

    def _get_line_segment_recursive(self, line_segments,line_colours, tree, eoffset):
        """
        add the line segment connecting this tree to its parent
        """
        color_default = (0., 0., 0.)
        if tree.parent is None:
            # this is a top level tree.  Add a short decorative vertical line
            if "children_not_connected" in tree.data:
                # this tree is simply a container, add the line to the subtrees
                treelist = tree.subtrees
            else:
                treelist = [tree]
            
            dy = self.energy_levels[-1] - self.energy_levels[-2]
            for t in treelist:
                x = t.data["x"]
                y = t.data["ethresh"]
                line_segments.append(([x,x], [y,y+dy]))
                line_colours.append(color_default)
        else:
            # add two line segments.  A vertical one to yhigh
            #  ([x, x], [y, yhigh])
            # and an angled one connecting yhigh with the parent
            #  ([x, xparent], [yhigh, yparent])
            xparent = tree.parent.data['x']
            xself = tree.data['x']
            yparent = tree.parent.data["ethresh"]

            if tree.is_leaf():
                yself = self._getEnergy(tree.data["minimum"])
            else:
                yself = tree.data["ethresh"]
            
            # determine yhigh from eoffset
            yhigh = yparent - eoffset
            if yhigh <= yself:
                draw_vertical = False
                yhigh = yself
            else:
                draw_vertical = True
            
            # determine the line color
            try: 
                color = tree.data['colour']
            except KeyError:
                color = color_default
            
            # draw vertical line
            if tree.is_leaf() and not draw_vertical:
                # stop diagonal line earlier to avoid artifacts
                # change the x position so that the angle of the line
                # doesn't change
                if not "_x_updated" in tree.data:
                    dxdy = (xself - xparent) / eoffset
                    xself = dxdy * (yparent - yself) + xparent
                    tree.data['x'] = xself
                    tree.data["_x_updated"] = True
            else: 
                #add vertical line segment
                line_segments.append( ([xself,xself], [yself, yhigh]) )
                line_colours.append(color)
#                print "coloring vertical line", tree
            
            # draw the diagonal line
            if not tree.parent.data.has_key("children_not_connected"):
                line_segments.append( ([xself, xparent], [yhigh, yparent]) )
                line_colours.append(color)

        for subtree in tree.get_subtrees():
            self._get_line_segment_recursive(line_segments, line_colours, subtree, eoffset)

        
    def _get_line_segments(self, tree, eoffset=-1.):
        """
        get all the line segments for drawing the connection between 
        each minimum to it's parent node.
        """
        line_segments = []
        line_colours = []
        self._get_line_segment_recursive(line_segments, line_colours, tree, eoffset)
        assert len(line_segments) == len(line_colours)
        return line_segments, line_colours
    
    
    ##########################################################################
    # functions for determining which minima to include in the 
    # disconnectivity graph
    ##########################################################################
    
    def _remove_nodes_with_few_edges(self, graph, nmin):
        rmlist = [n for n in graph.nodes() if graph.degree(n) < nmin]
        if len(rmlist) > 0:
            if self.gmin0 is not None:
                if self.gmin0 in rmlist:
                    print "global minimum has", graph.degree(self.gmin0), "edges, not showing in graph"
            print "removing", len(rmlist), "minima from graph with fewer than", nmin, "edges"
            for n in rmlist:
                graph.remove_node(n)
        return graph

    
    def _remove_high_energy_minima(self, graph, emax):
        if emax is None: return graph
        rmlist = [m for m in graph.nodes() if self._getEnergy(m) > emax]
        if len(rmlist) > 0:
            print "removing %d nodes with energy higher than"%len(rmlist), emax
        for m in rmlist:
            graph.remove_node(m)
        return graph

    def _remove_high_energy_transitions(self, graph, emax):
        if emax is None: return graph
        rmlist = [edge for edge in graph.edges() \
                  if self._getEnergy(self._getTS(edge[0], edge[1])) > emax]
        if len(rmlist) > 0:
            print "removing %d edges with energy higher than"%len(rmlist), emax
        for edge in rmlist:
            graph.remove_edge(edge[0], edge[1])
        return graph

    def _reduce_graph(self, graph, min0list):
        """determine how much of the graph to include in the disconnectivity graph
        """
        used_nodes = []
        #make sure we include the subgraph containing min0
        if len(min0list) == 0:
            #use the biggest connected cluster
            cc = nx.connected_components(graph)
            used_nodes += cc[0] #list is ordered by size of cluster
        else:
            for min0 in min0list:
                used_nodes += nx.node_connected_component(graph, min0)
        
        if self.subgraph_size is not None:
            node_lists = nx.connected_components(graph)
            for nodes in node_lists:
                if len(nodes) >= self.subgraph_size:
                    used_nodes += nodes

        newgraph = graph.subgraph(used_nodes)
        return newgraph

    ##########################################################################
    # general functions
    ##########################################################################
    
    
    def get_minima_layout(self):
        """
        return the x position of the minima        
        """
        leaves = self.tree_graph.get_leaves()
        minima = [leaf.data["minimum"] for leaf in leaves]
        xpos = [leaf.data["x"] for leaf in leaves]
        return xpos, minima
    
    def get_tree_layout(self):
        '''
        Returns the x position of the trees
        ''' 
        id = []

        for l in range(len(self.tree_list)):
            id += [tuple([l,i]) for i in range(len(self.tree_list[l]))]
        x_pos = [self.tree_list[l][i].data['x'] for l, i in id] 
        energies = [self.tree_list[l][i].data['ethresh'] for l, i in id]

        return id, x_pos, energies
        
    def _get_energy_levels(self, graph):
        """
        combine input and the graph data to determine what the 
        energy levels will be.
        """
        
        if hasattr(self, "elevels"):
            return self.elevels
        
        #define the energy levels
        elist = [self._getEnergy(self._getTS(*edge)) for edge in graph.edges()]
        if len(elist) == 0:
            raise Exception("there are no edges in the graph.  Is the global minimum connected?")
        emin = min(elist)
        if self.Emax is None:
            emax = max(elist)
        else:
            emax = self.Emax
        de = (emax - emin) / (self.nlevels-1)
        #the upper edge of the bins
        elower = [emin + de*(i) for i in range(self.nlevels)]
        elevels = elower.append(emin + de*self.nlevels)
        
        return elower

       
    
    def calculate(self):
        """
        do the calculations necessary to draw the diconnectivity graph
        """
        graph = self.graph
        assert graph.number_of_nodes() > 0, "graph has no minima"
        assert graph.number_of_edges() > 0, "graph has no transition states"
        
        # we start with applying the energy cutoff, otherwise reduce
        # graph does not work as intended
        graph = self._remove_high_energy_minima(graph, self.Emax)
        graph = self._remove_high_energy_transitions(graph, self.Emax)
        assert graph.number_of_nodes() > 0, "after applying Emax, graph has no minima"
        assert graph.number_of_edges() > 0, "after applying Emax, graph has no minima" 
        
        #find a reduced graph with only those connected to min0
#        nodes = nx.node_connected_component(self.graph, self.min0)
#        self.graph = self.graph.subgraph(nodes)
        graph = self._reduce_graph(graph, self.min0list)
        
        #define the energy levels
        elevels = self._get_energy_levels(graph)
        self.energy_levels = elevels
        
        #remove more nodes
        graph = self._remove_high_energy_minima(graph, elevels[-1])
        graph = self._remove_high_energy_transitions(graph, elevels[-1])
        graph = self._remove_nodes_with_few_edges(graph, 1)
        
        assert graph.number_of_nodes() > 0, "after cleaning up the graph, graph has no minima"
        assert graph.number_of_edges() > 0, "after cleaning up the graph, graph has no edges" 

        #make the tree graph defining the discontinuity of the minima
        tree_graph = self._make_tree(graph, elevels)
        
        #assign id to trees
        # this is needed for coloring basins
#        self._assign_id(tree_graph)
        
        #layout the x positions of the minima and the nodes
        self._layout_x_axis(tree_graph)

        #get the line segments which will be drawn to define the graph
        eoffset = (elevels[-1] - elevels[-2]) * self.node_offset  #this should be passable
#        line_segments = self._get_line_segments(tree_graph, eoffset=eoffset)
        
        
        self.eoffset = eoffset
        self.tree_graph = tree_graph
#        self.line_segments = line_segments
    
    def plot(self, show_minima=False, show_trees=False, linewidth=0.5, axes=None):
        """draw the disconnectivity graph using matplotlib
        
        don't forget to call calculate() first
        
        also, you must call pyplot.show() to actually see the plot
        """
        from matplotlib.collections import LineCollection
        import matplotlib.pyplot as plt
        
        self.line_segments, self.line_colours = self._get_line_segments(self.tree_graph, eoffset=self.eoffset)

        # get the axes object        
        if axes is not None:
            ax = axes
        else:
            fig = plt.figure(figsize=(6,7))
            fig.set_facecolor('white')
            ax = fig.add_subplot(111, adjustable='box')

        #set up how the figure should look
        ax.tick_params(axis='y', direction='out')
        ax.yaxis.tick_left()
        ax.spines['left'].set_color('black')
        ax.spines['left'].set_linewidth(0.5)
        ax.spines['top'].set_color('none')
        ax.spines['bottom'].set_color('none')
        ax.spines['right'].set_color('none')
#        plt.box(on=True)

        #draw the minima as points
        if show_minima: 
            xpos, energies = self.get_minima_layout()     
            ax.plot(xpos, energies, 'o')
        
        # draw the line segments 
        # use LineCollection because it's much faster than drawing the lines individually 
        linecollection = LineCollection([ [(x[0],y[0]), (x[1],y[1])] for x,y in self.line_segments])
        linecollection.set_linewidth(linewidth)
        linecollection.set_color(self.line_colours)
        ax.add_collection(linecollection)
        
        # scale the axes appropriately
        ax.relim()
        ax.autoscale_view(scalex=True, scaley=True, tight=None)
        ax.set_ylim(top=self.Emax)
        #remove xtics            
        ax.set_xticks([])        
        
        
    
