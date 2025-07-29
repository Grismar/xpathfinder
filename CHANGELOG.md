# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/latest/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.4] - 2021-07-30

### Added
- add bracket matching in the code editor
- add auto-indent on new lines in the code editor
- add appropriate indent size on Tab

### Changes
- add Exit option to the file menu
- clean up layout across panels
- change editor style to be more suitable for code editing

## [0.1.3] - 2021-07-29

### Fixed
- enable options after opening a file

## [0.1.2] - 2021-07-29

### Added
- Execute XPath after successful code execution
- Split the output history into two panes: outputs and messages
- Add Save, Revert, Undo, and Redo buttons to the file menu
- Add support for undo/redo on the file after code execution
- Optional namespace scrubbing on XPath results
- Ctrl+Enter to execute LLM Query, XPath, or Python from the editor

### Changed
- Stop automatic code execution after LLM query

### Fixed
- Improve help text on Python editor and XPath editor

## [0.1.0] - 2025-07-27

### Added

Initial release, basic functionality:
- Load and save XML files
- XPath editor with live results
- Python code editor
- LLM query panel for XPath and Python generation
- Selection viewer for XPath results
- Output history for LLM responses and script output
- Namespace prefix control for default namespace
- Resizable panes via splitters
- Basic file picker for loading XML files

[Unreleased]: /../../../
[0.1.4]: /../../../tags/0.1.4
[0.1.1]: /../../../tags/0.1.1
