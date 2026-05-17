"""A deliberately messy module so ruff has work to do.

Every violation in this file is autofixable by `ruff check --fix` and
`ruff format`. The quickstart proves the closed loop by watching ruff
take this file to zero violations in a single evolution round.
"""
import os
import sys
import json
from pathlib import     Path



def greet( name ) :
    if name == None :
        return "hello, stranger"
    return "hello, "+name


def add(   a,b  ) :
    return a+b


def is_ready(flag):
    if flag == True:
        return "ready"
    if flag == False:
        return "not ready"
    return "unknown"
