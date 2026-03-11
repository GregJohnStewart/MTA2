#!/bin/python
#
# Recursive RHMTA runner
#
# Requirements:
#  - argparse
#  - argcomplete
#  - PyYaml
#
import argparse
import logging

from gi.overrides.BlockDev import cls

logging.basicConfig(
    filename='mta2.log',
    filemode='w',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', # Use %(name)s
    level=logging.DEBUG
)

class MtaResultCollator:
    logger = logging.getLogger(__name__)

class DepTreeCollator:
    logger = logging.getLogger(__name__)


class GitPuller:
    logger = logging.getLogger(__name__)

class RecMta:
    logger = logging.getLogger(__name__)


argParser = argparse.ArgumentParser(
    # prog='mta2',
    description='Recursive MTA Runner',
)


