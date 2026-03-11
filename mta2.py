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
import csv
import io
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    filename='mta2.log',
    filemode='w',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Use %(name)s
    level=logging.DEBUG
)


class MtaResultCollator:
    logger = logging.getLogger(__name__)


class DepTreeCollator:
    """
    Class to encapsulate code to collate dependency tree outputs.

    "Main" method is "process"
    """
    logger = logging.getLogger(__name__)

    @classmethod
    def readTreeFiles(cls, fileName: str, directory: str = ".") -> dict:
        """
        Reads all dependency tree files in directory given.

        Schema of output::

            {
                "<fileName>": {}//content of dep tree file "children" field; actual dependencies of project
                // ... foreach file found
            }

        :param directory: The directory to search for dependency tree output files
        :param fileName: The dependency tree output file name to search for
        :return: A Dict of dependencies found
        """
        cls.logger.info("Reading in dependency tree files")

        output = {}

        depTreeFiles = [
            str(path_obj) for path_obj in Path(directory).rglob(fileName)
            if path_obj.is_file()
        ]

        if len(depTreeFiles) == 0:
            logging.error("No dependency tree files found")
            print("ERROR: No dependency tree files found.", file=sys.stderr)
            raise "No dependency tree files found."

        for curFile in depTreeFiles:
            cls.logger.info("Found file: " + curFile)
            curResults = None
            with open(curFile, 'r') as inFile:
                curResults = json.load(inFile)
            output[curFile] = curResults

        cls.logger.info("Finished reading in dependency tree files. # files: %s", len(output))
        return output

    @classmethod
    def processChild(cls, output: dict, file: str, child: dict) -> None:
        """
        Recursive call to process dependencies and their sub-dependencies (children)
        :param output: The main output dependency dict we are adding to
        :param file: The current file these dependencies are read from
        :param child: The current child dependency to work on
        :return: Nothing, processes in-place to the "output" parameter
        """
        dependency = child["groupId"] + ":" + child["artifactId"] + ":" + child["version"]

        depObj = {}
        if dependency in output:
            cls.logger.debug("Found dupe dependency: %s", dependency)
            depObj = output[dependency]
        else:
            depObj = {
                "files": []
            }
            output[dependency] = depObj
        depObj["files"].append(file)

        if "children" in child:
            for curSubChild in child["children"]:
                cls.processChild(output, file, curSubChild)

    @classmethod
    def collateDeps(cls, depTrees: dict) -> dict:
        """
        Collated the raw dependencies from :meth:`.readTreeFiles`.

        Schema of output::

            {
                "<dependency>": [
                    "files": [
                      // ... list of files the dependency is featured in
                    ]
                ]
                // ... foreach file found
            }

        :param depTrees: Output from :meth:`.readTreeFiles`
        :return:
        """
        cls.logger.info("Collating dependency trees")

        output = {}

        for curFile, depTree in depTrees.items():
            cls.logger.info("Processing dependency tree from file: %s", curFile)

            if "children" in depTree:
                for curSubChild in depTree["children"]:
                    cls.processChild(output, curFile, curSubChild)
            else:
                cls.logger.info("File had no dependencies.")
        # sort results
        output = dict(sorted(output.items()))

        cls.logger.info("Done collating dependency trees. # unique dependencies: %s", len(output))
        return output

    @classmethod
    def outputResult(cls, deps, outFile: str, outFormat: str = "-") -> None:
        """
        Outputs the results to a file/stream
        :param deps: The dependencies to output
        :param outFile: The file to output the dependencies to. "-" for stdout. For files, only ".json" and ".csv" are supported.
        :param outFormat: The format to output in. "-" to glean from outFile ("json" default, if stdout). Only "json" and "csv" are supported.
        :return: No return output
        """
        cls.logger.info("Outputting dependencies.")

        outStr = None

        if outFormat == "-":
            if outFile.endswith(".json"):
                outFormat = "json"
            elif outFile.endswith(".csv"):
                outFormat = "csv"
            cls.logger.debug("Determined output format as: %s", outFormat)

        if outFormat == "json":
            cls.logger.info("Outputting as json")
            outStr = json.dumps(deps, indent=4)
        elif outFormat == "csv":
            cls.logger.info("Outputting as csv")

            outStr = io.StringIO()
            csvData = []
            for curDep, depObj in deps.items():
                csvData.append({
                    "dependency": curDep,
                    "files": ",".join(depObj["files"]),
                })
            cls.logger.debug("CSV data: %s", csvData)

            writer = csv.DictWriter(
                outStr,
                extrasaction="ignore",
                fieldnames=csvData[0].keys()
            )
            writer.writeheader()
            writer.writerows(csvData)
            outStr = outStr.getvalue()
            cls.logger.info("Finished converting to csv")
        else:
            cls.logger.error("Unknown output format: %s", outFormat)
            print("ERROR: Unknown output format: " + outFormat)
            raise "Unknown output format: " + outFormat

        if outFile == "-":
            cls.logger.info("Outputting to stdout")
            print(outStr)
        else:
            cls.logger.info("Outputting to file: %s", outFile)
            with open(outFile, "w") as outFileD:
                outFileD.write(outStr)
            cls.logger.info("Finished writing to file: %s", outFile)
        cls.logger.info("Done outputting results.")

    @classmethod
    def process(cls, fileName: str = "depTree.json", directory: str = ".", outFile: str | None = None, outFormat: str = "-") -> dict:
        """
        Processes a directory for their dependencies. Collates them into an organized dict of individual, unique dependencies.

        :param directory: The directory to search. Defaults to current working directory.
        :param fileName: The name of the dependency tree output files in th directory.
        :param outFile:
        :param outFormat:
        :return:
        """
        cls.logger.info("Processing dependency tree.")

        deps = cls.readTreeFiles(fileName, directory=directory)
        deps = cls.collateDeps(deps)
        if outFile is not None:
            cls.outputResult(deps, outFile, outFormat)

        cls.logger.info("Done processing dependency tree.")
        return deps


class GitPuller:
    logger = logging.getLogger(__name__)


class RecMta:
    logger = logging.getLogger(__name__)


argParser = argparse.ArgumentParser(
    # prog='mta2',
    description='Recursive MTA Runner',
)

args = argParser.parse_args()
