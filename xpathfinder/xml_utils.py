from typing import Union, List, Optional
from lxml import etree

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


def pretty_print(node: Union[Node, Document, object]) -> str:
    """
    Convert an XML node (or any object) to a readable string.

    Tries to pretty-print XML elements, falls back to str().
    """
    try:
        return etree.tostring(node, pretty_print=True, encoding='unicode')
    except (TypeError, ValueError):
        return str(node)
