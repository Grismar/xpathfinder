# XPathfinder

An interactive GUI tool to explore and manipulate XML documents with XPath and Python — powered by a local Python execution environment and optional LLM assistance.

See the [changelog](CHANGELOG.md) for recent changes.

## Features

- **Load & Save** XML documents via file picker or CLI argument  
- **XPath Editor** with undo/redo/clear controls  
- **Python Code Editor** for ad‑hoc scripts operating on the XML or XPath selection  
- **LLM Query Panel** (OpenAI GPT) to generate or refine XPath expressions and Python snippets  
- **Selection Viewer** showing the live result of your XPath query  
- **Output History** capturing LLM responses, script output, and save/open events  
- **Namespace Prefix Control** to bind the default namespace to a user‑chosen prefix  
- **Resizable Panes** via splitters  

## Installation

Ensure you have `Python 3.9+` and [Git][git] installed.

Create and [activate a virtual environment][venv], then install the package:
```
git clone https://github.com/Grismar/xpathfinder.git
cd xpathfinder
pip install -e .
```

Using conda, instead of `pip install .` you can create an environment and install Python and the packages from the provided `environment.yml` file in one go:
```
conda create -n xpathfinder -f environment.yml
conda activate xpathfinder
```

## Usage
From the active environment, run the application with:
```
python -m xpathfinder [<path_to_xml_file>]
```

Or simply:
```
xpf [<path_to_xml_file>]
```

This starts the GUI, optionall loading the specified XML file. If no file is provided, you can load one later via the file picker.

The basic workflow is:
1. Load an XML file (or start with an empty document)
2. Use the XPath editor to write or modify XPath expressions
3. View the results in the selection viewer
4. Use the Python code editor to write scripts that operate on the XML or XPath selection
5. Optionally, use the LLM query panel to generate or refine XPath expressions and Python snippets
6. Save your XML document or the output of your scripts

### Namespace Handling
If your XML document uses namespaces, you can bind the default namespace to a user‑chosen prefix in the Namespace Prefix Control. This allows you to use that prefix in your XPath expressions.

For example, say your XML document has a default namespace, like the start of this XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<workflowDescriptors xmlns="http://www.wldelft.nl/fews" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.wldelft.nl/fews  https://fewsdocs.deltares.nl/schemas/version1.0/workflowDescriptors.xsd" version="1.0">
```
You can bind the default namespace to a prefix, say `fews`, in the Namespace Prefix Control. Then you can use that prefix in your XPath expressions like this:
```xpath
.//fews:workflowDescriptor
```
XPathfinder will detect the need for a namespace prefix and defaults to `ns` if no prefix is specified.

### LLM Assistance

The LLM Query Panel allows you to interact with an OpenAI GPT model to generate or refine XPath expressions and Python snippets. You can ask it to:
- Generate XPath expressions based on natural language queries
- Refine existing XPath expressions
- Generate Python code snippets that operate on the XML or XPath selection
- Provide explanations for XPath expressions or Python code

Set your OpenAI API key in the `OPENAI_API_KEY` environment variable to enable LLM assistance, or if on Windows (preferably), set your API key through the menu, which will store it using the Windows Credential Manager.

For users of [https://github.com/Grismar/gpt], note that this app shares the same key and stores it in the same location. If you already use that tool, XPathfinder will automatically work, and vice versa. 

[git]: https://git-scm.com/
[venv]: https://docs.python.org/3/library/venv.html
