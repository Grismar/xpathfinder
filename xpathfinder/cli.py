import argparse
from xpathfinder.app import XPathFinderApp

def main():
    parser = argparse.ArgumentParser(description="XPathFinder, XPath & Python XML Editor")
    parser.add_argument("xml_file", nargs="?", help="Path to XML file")
    args = parser.parse_args()
    app = XPathFinderApp(xml_file=args.xml_file)
    app.run()

if __name__ == "__main__":
    main()
