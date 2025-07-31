from typing import Union, List, Optional
from lxml import etree
from collections import defaultdict

# Aliases for XML types (protected internals referenced once)
# noinspection PyProtectedMember
Document = etree._ElementTree
# noinspection PyProtectedMember
Node = etree._Element


def parse_xml(path: str) -> tuple[Document, Optional[dict], Optional[str]]:
    """
    Parse an XML file and return an ElementTree for querying.

    Args:
        path: Path to the XML file.

    Returns:
        An lxml ElementTree representing the parsed XML.
    """
    parser = etree.XMLParser(remove_blank_text=True)

    # if there is a default namespace, assign a unique prefix for use in XPath queries
    doc = etree.parse(path, parser)
    nsmap = doc.getroot().nsmap
    default_ns_uri = nsmap.get(None)

    if default_ns_uri:
        ns = 'ns'
        while ns in nsmap:
            ns += '_'
        nsmap = {(ns if k is None else k): v for k, v in nsmap.items()}
    else:
        nsmap, ns = None, None

    return etree.parse(path, parser), nsmap, ns


def apply_xpath(doc: Union[Document, Node], expr: str, namespaces: dict[str, str] = None) -> List[Union[Node, str, float, bool]]:
    """
    Apply an XPath expression against the provided document or element.

    Args:
        doc: An ElementTree or Element to query.
        expr: XPath expression string.
        namespaces: Optional dictionary of namespace prefixes to URIs.

    Returns:
        A list of matched nodes or values.
    """
    return doc.xpath(expr, namespaces=namespaces)


def strip_namespaces(source_elem):
    if source_elem.tag is etree.Comment:
        return etree.Comment(source_elem.text)

    if '}' in source_elem.tag:
        tag_name = source_elem.tag.split('}', 1)[1]
    else:
        tag_name = source_elem.tag

    new_elem = etree.Element(tag_name)

    if source_elem.text:
        new_elem.text = source_elem.text
    if source_elem.tail:
        new_elem.tail = source_elem.tail

    for key, value in source_elem.attrib.items():
        if key.startswith('xmlns') or key == 'xmlns':
            continue
        if '}' in key:
            clean_key = key.split('}', 1)[1]
        else:
            clean_key = key
        new_elem.set(clean_key, value)

    for child in source_elem:
        clean_child = strip_namespaces(child)
        new_elem.append(clean_child)

    return new_elem


def pretty_print(node: Union[Node, Document, object], strip_ns: bool = False) -> str:
    try:
        if strip_ns:
            node = strip_namespaces(node)
        return etree.tostring(node, pretty_print=True, encoding='unicode')
    except (TypeError, ValueError):
        return str(node)

def summarize_xml_structure(doc: Document) -> str:
    root = doc.getroot()

    summary_lines = []
    tag_tree = defaultdict(lambda: {"count": 0, "attributes": set(), "children": defaultdict(int)})

    def traverse(elem, parent_tag=None):
        if not isinstance(elem.tag, str):  # Skip non-element nodes, like comments or processing instructions
            return
        tag = etree.QName(elem).localname
        tag_tree[tag]["count"] += 1
        tag_tree[tag]["attributes"].update(elem.attrib.keys())
        if parent_tag:
            tag_tree[parent_tag]["children"][tag] += 1
        for child in elem:
            traverse(child, tag)

    traverse(root)

    def format_summary(tag, indent=0, seen=None):
        if seen is None:
            seen = set()

        children = tag_tree[tag]["children"]
        attrs = tag_tree[tag]["attributes"]
        line = "  " * indent + f"- <{tag}>"
        if attrs:
            line += f" [attributes: {', '.join(sorted(attrs))}]"
        summary_lines.append(line)

        if tag in seen:
            summary_lines.append("  " * (indent + 1) + "(recursive element)")
            return

        new_seen = seen | {tag}
        for child_tag in sorted(children.keys()):
            format_summary(child_tag, indent + 1, new_seen)

    root_tag = etree.QName(root).localname
    summary_lines.append(f"<{root_tag}>")
    for child_tag in sorted(tag_tree[root_tag]["children"].keys()):
        format_summary(child_tag, 1)

    return "\n".join(summary_lines)
