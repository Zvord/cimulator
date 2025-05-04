"""
Type definitions for the Cimulator project.

This module contains type aliases used throughout the project to improve
code readability and maintainability.
"""

from typing import Dict, Any, List, Union, Optional, Set

# Common type aliases
ConfigDict = Dict[str, Any]
JobDict = Dict[str, Any]
VariablesDict = Dict[str, Any]
JobSourcesDict = Dict[str, Union[str, List[str]]]
JobOccurrencesDict = Dict[str, List[str]]
