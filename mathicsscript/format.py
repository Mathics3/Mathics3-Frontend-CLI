"""
Format Mathics3 objects
"""

import math
import random
from tempfile import NamedTemporaryFile
from typing import Callable

import networkx as nx
from mathics.core.atoms import String
from mathics.core.expression import BoxError, Expression
from mathics.core.symbols import Symbol
from mathics.core.systemsymbols import (
    SymbolAborted,
    SymbolExport,
    SymbolExportString,
    SymbolFailed,
    SymbolFullForm,
    SymbolGraphics,
    SymbolGraphics3D,
    SymbolImage,
    SymbolInterpretationBox,
    SymbolMathMLForm,
    SymbolOutputForm,
    SymbolPlot,
    SymbolStandardForm,
    SymbolTeXForm,
)
from mathics.format.box import format_element
from mathics.session import get_settings_value
from mathicsscript.asymptote import Asy, write_asy_and_view

PyMathicsGraph = Symbol("Pymathics`Graph")

try:
    from matplotlib import __version__ as matplotlib_version
except ImportError:
    matplotlib_version = None

try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    import matplotlib.image as mpimg
except ImportError:
    mpimg = None

try:
    from cairosvg import svg2png
except ImportError:
    svg2png = None

have_asymptote = False
try:
    asymptote_graph = Asy(show_help=False)
except Exception:
    asymptote_graph = None
else:
    have_asymptote = True
    asymptote_graph.size(200)


def format_output(obj, expr, format=None):
    """
    Handle unformatted output using the *specific* capabilities of mathicsscript

    evaluation.py format_output() from which this was derived is similar but
    it can't make use of a front-ends specific capabilities.
    """

    def eval_boxed(result, fn: Callable, obj, **options):
        try:
            boxed = fn(evaluation=obj, **options)
        except BoxError:
            boxed = None
            if not hasattr(obj, "seen_box_error"):
                obj.seen_box_error = True
                obj.message(
                    "General",
                    "notboxes",
                    Expression(SymbolFullForm, result).evaluate(obj),
                )

        return boxed

    if format is None:
        format = obj.format

    if isinstance(format, dict):
        return dict((k, obj.format_output(expr, f)) for k, f in format.items())

    expr_type = expr.get_head_name()
    expr_head = expr.get_head()

    if expr_head is SymbolMathMLForm:
        format = "xml"
        elements = expr.elements
        if len(elements) == 1:
            expr = elements[0]
    elif expr_head is SymbolTeXForm:
        format = "tex"
        elements = expr.elements
        if len(elements) == 1:
            expr = elements[0]
        render_TeXForm = get_settings_value(
            obj.definitions, "Settings`$UseMatplotlib"
        ) and get_settings_value(obj.definitions, "Settings`$RenderTeXForm")
        if render_TeXForm:
            boxed = format_element(expr, obj, SymbolTeXForm)
            if hasattr(boxed, "head") and boxed.head is SymbolInterpretationBox:
                inner_box = boxed.elements[0]
                box_str_sans_quotes = inner_box.value[1:-1]
                box_str_display_math = rf"${box_str_sans_quotes}$"
                try:
                    # Create a figure and axis with no visible borders
                    fig, ax = plt.subplots(figsize=(3, 2))
                    ax.axis("off")
                    # Render the LaTeX string in the center
                    # 'transform=ax.transAxes' ensures 0.5 is the exact middle of the window
                    ax.text(
                        0.5,
                        0.5,
                        box_str_display_math,
                        size=50,
                        ha="center",
                        va="center",
                        transform=ax.transAxes,
                    )
                    plt.show()
                    return String(box_str_sans_quotes)
                except:  # noqa
                    pass

    elif (
        expr_head is SymbolImage
        and get_settings_value(obj.definitions, "Settings`$UseMatplotlib")
        and plt
    ):
        temp_png = NamedTemporaryFile(
            mode="w+b", suffix=".png", prefix="mathicsscript-"
        )
        try:
            png_expr = Expression(
                SymbolExport, String(temp_png.name), expr, String("PNG")
            )
            result = png_expr.evaluate(obj)
            plt.axes().set_axis_off()
            img = mpimg.imread(temp_png)
            cmap = "gray" if expr.color_space == "Grayscale" else None
            plt.imshow(img, cmap=cmap)
            plt.show()
        except:  # noqa
            pass
        temp_png.close()

    elif (
        expr_head in (SymbolGraphics, SymbolPlot)
        and get_settings_value(obj.definitions, "Settings`$UseMatplotlib")
        and plt
        and svg2png
    ):
        svg_expr = Expression(SymbolExportString, expr, String("SVG"))
        svg_str = svg_expr.evaluate(obj).to_python(string_quotes=False)
        temp_png = NamedTemporaryFile(
            mode="w+b", suffix=".png", prefix="mathicsscript-"
        )
        try:
            svg2png(bytestring=svg_str, write_to=temp_png.name)
            plt.axes().set_axis_off()
            img = mpimg.imread(temp_png)
            plt.imshow(img)
            plt.show()
            temp_png.close()
        except:  # noqa
            pass
        return expr_type
    elif (
        expr_head in (SymbolGraphics, SymbolPlot, SymbolGraphics3D)
        and have_asymptote
        and get_settings_value(obj.definitions, "Settings`$UseAsymptote")
    ):
        asy_expr = Expression(SymbolExportString, expr, String("asy"))
        asy_str = asy_expr.evaluate(obj).to_python(string_quotes=False)

        # Alternate older version
        # asymptote_graph.erase()
        # asymptote_graph.send(asy_str)

        write_asy_and_view(asy_str)
        return expr_type

    if expr is SymbolAborted:
        obj.out = ["$Aborted"]
        obj.last_eval = SymbolAborted
        return "$Aborted"
    elif expr is SymbolFailed:
        obj.out = ["$Failed"]
        obj.last_eval = SymbolFailed
        return "$Failed"
    if format == "text":
        if isinstance(expr, String):
            return expr.value
        result = expr.format(obj, SymbolOutputForm)
    elif format == "xml":
        result = Expression(SymbolStandardForm, expr).format(obj, SymbolMathMLForm)
    elif format == "tex":
        result = Expression(SymbolStandardForm, expr).format(obj, SymbolTeXForm)
    elif format == "error":
        # We may do fancier things in the future.
        if isinstance(expr, String):
            return expr.value
        result = expr.format(obj, SymbolOutputForm)
    elif format == "unformatted":
        if expr_head is PyMathicsGraph and hasattr(expr, "G"):
            return format_graph(expr.G)
        else:
            result = expr.format(obj, SymbolOutputForm)
    else:
        raise ValueError

    try:
        boxes = result.to_text(evaluation=obj)
    except BoxError:
        boxes = None
        if not hasattr(obj, "seen_box_error"):
            obj.seen_box_error = True
            obj.message(
                "General", "notboxes", Expression(SymbolFullForm, result).evaluate(obj)
            )
    return boxes


cached_pair = None


def hierarchy_pos(
    G, root=None, width=1.0, vert_gap=0.2, vert_loc=0, leaf_vs_root_factor=0.5
):
    """Position nodes in tree layout. The root is at the top.

    Based on Joel's answer at https://stackoverflow.com/a/29597209/2966723,
    but with some modifications.

    There are two basic approaches we think of to allocate the horizontal
    location of a node.

    - Top down: we allocate horizontal space to a node.  Then its ``k``
      descendants split up that horizontal space equally.  This tends to result
      in overlapping nodes when some have many descendants.
    - Bottom up: we allocate horizontal space to each leaf node.  A node at a
      higher level gets the entire space allocated to its descendant leaves.
      Based on this, leaf nodes at higher levels get the same space as leaf
      nodes very deep in the tree.

    We use use both of these approaches simultaneously with ``leaf_vs_root_factor``
    determining how much of the horizontal space is based on the bottom up
    or top down approaches.  ``0`` gives pure bottom up, while 1 gives pure top
    down.

    From EoN (Epidemics on Networks): a fast, flexible Python package
    for simulation, analytic approximation, and analysis of epidemics
    on networks
    https://joss.theoj.org/papers/10.21105/joss.01731

    :Arguments:

    Parameters
    ----------
    G : NetworkX graph or list of nodes
        A position will be assigned to every node in G.
        The graph must be a tree.

    root : the root node of the tree

    - if the tree is directed and this is not given, the root will be found and used
    - if the tree is directed and this is given, then the positions will be
      just for the descendants of this node.
    - if the tree is undirected and not given, then a random choice will be used.

    width : horizontal space allocated for this branch - avoids overlap with other branches

    vert_gap : gap between levels of hierarchy

    vert_loc : vertical location of root

    leaf_vs_root_factor : used in calculating the _x_ coordinate of a leaf

    xcenter : horizontal location of root

    Examples
    --------
    >>> G = nx.binomial_tree(3)
    >>> nx.draw(G, pos=nx.hierarchy_layout(G, root=0))

    As the number of nodes gets large, the node size and node labels
    may need to be adjusted. The following shows how the minimum
    separation between nodes can be used to adjust node sizes.

    >>> G = nx.full_rary_tree(2, 127)
    >>> pos, min_sep = nx.hierarchy_layout_with_min_sep(G, root=0)
    >>> nx.draw(G, pos=pos, node_size=min_sep * 1500)

    Also see the NetworkX drawing examples at
    https://networkx.org/documentation/latest/auto_examples/index.html

    """
    if not nx.is_tree(G):
        raise TypeError("cannot use hierarchy_pos on a graph that is not a tree")

    global cached_pair
    if cached_pair is not None:
        return cached_pair

    # These get swapped if tree edge directions point to the root.
    descendants = nx.descendants
    out_degree = G.out_degree if hasattr(G, "out_degree") else G.degree
    neighbors = G.neighbors

    if root is None:
        if isinstance(G, nx.DiGraph):
            zero_outs = [n for n in G.out_degree() if n[1] == 0]
            if len(zero_outs) == 1 and len(G) > 2:
                # We unequivocally have a directed that points from leave to the root.
                # The case where we have a one or two node graph is ambiguous.
                root = list(nx.topological_sort(G))[-1]
                # Swap motion functions
                descendants = nx.ancestors
                out_degree = G.in_degree
                neighbors = G.predecessors
            else:
                root = next(
                    iter(nx.topological_sort(G))
                )  # allows back compatibility with nx version 1.11
                # root = next(nx.topological_sort(G))
        else:
            root = random.choice(list(G.nodes))

    def _hierarchy_pos(
        G,
        root,
        leftmost,
        width,
        leafdx=0.2,
        vert_gap=0.2,
        vert_loc=0,
        xcenter=0.5,
        rootpos=None,
        leafpos=None,
        parent=None,
    ):
        """
        see hierarchy_pos docstring for most arguments

        pos: a dict saying where all nodes go if they have been assigned
        parent: parent of this branch. - only affects it if non-directed

        """

        if rootpos is None:
            rootpos = {root: (xcenter, vert_loc)}
        else:
            rootpos[root] = (xcenter, vert_loc)
        if leafpos is None:
            leafpos = {}

        children = list(neighbors(root))
        leaf_count = 0
        if not isinstance(G, nx.DiGraph) and parent is not None:
            children.remove(parent)
        if len(children) != 0:
            rootdx = width / len(children)
            nextx = xcenter - width / 2 - rootdx / 2
            for child in children:
                nextx += rootdx
                rootpos, leafpos, newleaves = _hierarchy_pos(
                    G,
                    child,
                    leftmost + leaf_count * leafdx,
                    width=rootdx,
                    leafdx=leafdx,
                    vert_gap=vert_gap,
                    vert_loc=vert_loc - vert_gap,
                    xcenter=nextx,
                    rootpos=rootpos,
                    leafpos=leafpos,
                    parent=root,
                )
                leaf_count += newleaves

            leftmostchild = min((x for x, y in [leafpos[child] for child in children]))
            rightmostchild = max((x for x, y in [leafpos[child] for child in children]))
            leafpos[root] = ((leftmostchild + rightmostchild) / 2, vert_loc)
        else:
            leaf_count = 1
            leafpos[root] = (leftmost, vert_loc)
        #        pos[root] = (leftmost + (leaf_count-1)*dx/2., vert_loc)
        #        print(leaf_count)
        return rootpos, leafpos, leaf_count

    xcenter = width / 2.0
    if isinstance(G, nx.DiGraph):
        leafcount = len(
            [node for node in descendants(G, root) if out_degree(node) == 0]
        )
    elif isinstance(G, nx.Graph):
        leafcount = len(
            [
                node
                for node in nx.node_connected_component(G, root)
                if G.degree(node) == 1 and node != root
            ]
        )

    rootpos, leafpos, leaf_count = _hierarchy_pos(
        G,
        root,
        0,
        width,
        leafdx=width * 1.0 / leafcount,
        vert_gap=vert_gap,
        vert_loc=vert_loc,
        xcenter=xcenter,
    )
    pos = {}
    for node in rootpos:
        pos[node] = (
            leaf_vs_root_factor * leafpos[node][0]
            + (1 - leaf_vs_root_factor) * rootpos[node][0],
            leafpos[node][1],
        )
    #    pos = {node:(leaf_vs_root_factor*x1+(1-leaf_vs_root_factor)*x2, y1) for ((x1,y1), (x2,y2)) in (leafpos[node], rootpos[node]) for node in rootpos}
    xmax = max(x for x, y in pos.values())
    y_list = {}
    for node in pos:
        x, y = pos[node] = (pos[node][0] * width / xmax, pos[node][1])
        y_list[y] = y_list.get(y, set([]))
        y_list[y].add(x)

    min_sep = xmax
    for y in y_list.keys():
        x_list = sorted(y_list[y])
        n = len(x_list) - 1
        if n <= 0:
            continue
        min_sep = min([x_list[i + 1] - x_list[i] for i in range(n)] + [min_sep])
    cached_pair = pos, min_sep
    return cached_pair


node_size = 300  # this is networkx's default size


def tree_layout(G):
    global node_size
    root = G.root if hasattr(G, "root") else None
    pos, min_sep = hierarchy_pos(G, root=root)
    node_size = min_sep * 2000
    return pos


def spiral_equidistant_layout(G, *args, **kwargs):
    return nx.spiral_layout(G, equidistant=True, *args, **kwargs)


NETWORKX_LAYOUTS = {
    "circular": nx.circular_layout,
    "kamada_kawai": nx.kamada_kawai_layout,
    "multipartite": nx.multipartite_layout,
    "planar": nx.planar_layout,
    "random": nx.random_layout,
    "shell": nx.shell_layout,
    "spectral": nx.spectral_layout,
    "spiral": nx.spiral_layout,
    "spiral_equidistant": spiral_equidistant_layout,
    "spring": nx.spring_layout,
    "tree": tree_layout,
}

LAYOUT_DENSITY_EXPONENT = {"circular": 0.9, "spiral_equidistant": 0.7, "spiral": 0.6}


def clamp(value, min=-math.inf, max=math.inf):
    if value <= min:
        return min
    if value >= max:
        return max
    return value


DEFAULT_NODE_SIZE = 300.0
DEFAULT_POINT_SIZE = 16


def harmonize_parameters(G, draw_options: dict):

    global node_size
    graph_layout = G.graph_layout if hasattr(G, "graph_layout") else ""

    if graph_layout == "tree":
        # Call this to compute node_size. Cache the
        # results
        tree_layout(G)
        draw_options["node_size"] = node_size
    elif graph_layout in ["circular", "spiral", "spiral_equidistant"]:
        exponent = LAYOUT_DENSITY_EXPONENT[graph_layout]
        node_size = draw_options["node_size"] = (2 * DEFAULT_NODE_SIZE) / (
            len(G) + 1
        ) ** exponent
        # print("XX", node_size, exponent)

    if draw_options.get("with_labels", False):
        draw_options["edgecolors"] = draw_options.get("edgecolors", "black")
        draw_options["node_color"] = draw_options.get("node_color", "white")

    if "width" not in draw_options:
        width = clamp(node_size / DEFAULT_NODE_SIZE, min=0.15)
        draw_options["width"] = width

    if "font_size" not in draw_options:
        # FIXME: should also take into consideration max width of label.
        font_size = clamp(
            int((node_size * DEFAULT_POINT_SIZE) / DEFAULT_NODE_SIZE), min=1, max=18
        )
        draw_options["font_size"] = font_size


def format_graph(G):
    """
    Format a Graph
    """
    # FIXME handle graphviz as well

    global node_size
    global cached_pair

    cached_pair = None

    graph_layout = G.graph_layout if hasattr(G, "graph_layout") else None
    node_shape = G.node_shape if hasattr(G, "node_shape") else "o"

    node_size = DEFAULT_NODE_SIZE
    draw_options = {
        "node_size": node_size,
        "node_shape": node_shape,
        # "with_labels": vertex_labels # Set below
        # "font_size": 12,        # Harmonized
        # "node_color": "white",  # Set below
        # "edgecolors": "black",  # Set below
        # "width": 5,             # Marmonized
    }

    vertex_labels = G.vertex_labels if hasattr(G, "vertex_labels") else False
    if vertex_labels:
        draw_options["with_labels"] = bool(vertex_labels)

    if hasattr(G, "title") and G.title:
        fig, ax = plt.subplots()  # Create a figure and an axes
        ax.set_title(G.title)

    layout_fn = None
    if graph_layout:
        if not isinstance(graph_layout, str):
            graph_layout = graph_layout.get_string_value()
        layout_fn = NETWORKX_LAYOUTS.get(graph_layout, None)
        if graph_layout in ["circular", "spiral", "spiral_equidistant"]:
            plt.axes().set_aspect("equal")

    harmonize_parameters(G, draw_options)

    if layout_fn:
        nx.draw(G, pos=layout_fn(G), **draw_options)
    else:
        nx.draw_shell(G, **draw_options)
    plt.show()
    return None
