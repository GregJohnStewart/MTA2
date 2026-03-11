#!/bin/python
#
# Recursive RHMTA runner
#
# Requirements:
#  - argparse
#  - argcomplete
#  - PyYaml
#
from pathlib import Path
import argparse
import copy
import csv
import io
import json
import logging
import sys
import argcomplete
import yaml

logging.basicConfig(
    filename='mta2.log',
    filemode='w',
    format='[%(asctime)s][%(name)-17s][%(levelname)-5s] %(message)s',  # Use %(name)s
    level=logging.DEBUG
)


class MtaResultToCsv:
    logger = logging.getLogger("MtaResultCollator")

    @classmethod
    def __readMtaResults(cls, mtaFile):
        cls.logger.info("Reading MTA Results.")

        mtaResults = None
        if mtaFile == "-":
            cls.logger.info("Reading MTA Results from stdin.")
            full_input = sys.stdin.read()
            mtaResults = yaml.safe_load(full_input)
        else:
            cls.logger.info("Getting MTA Results from file: %s", mtaFile)
            with open(mtaFile, "r") as inFile:
                mtaResults = yaml.safe_load(inFile)
        cls.logger.info("Done Reading MTA Results.")
        return mtaResults

    @classmethod
    def __deduplicate(cls):
        cls.logger.info("Deduplicating MTA Results.")

        out = []

    @classmethod
    def __mtaToCsv(cls, mtaResults: list, header=True) -> str:
        cls.logger.info("Converting MTA Results to CSV.")

        output = io.StringIO()
        data = []
        dedup = {}

        for curResult in mtaResults:
            cls.logger.info("Processing result: %s", curResult["name"])

            curTarget = {
                "name": curResult["name"],
                "description": curResult["description"]
            }

            for curViolationName, curViolationDict in curResult.get("violations", {}).items():
                violation = copy.deepcopy(curTarget)

                violation["violation"] = curViolationName
                violation["effort"] = curViolationDict.get("effort", "")
                violation["category"] = curViolationDict.get("category", "")
                violation["labels"] = ",".join(curViolationDict.get("labels", []))

                for curIncident in curViolationDict.get("incidents", []):
                    file = curIncident.get("uri", "")
                    lineNumber = curIncident.get("lineNumber", "-")
                    #dedup key to reference a single file with this particular violation
                    dedupKey = violation["name"] + violation['violation'] + file

                    if dedupKey in dedup.keys():
                        dedup[dedupKey]['lineNumbers'] += ","+str(lineNumber)
                    else:
                        violationOut = copy.deepcopy(violation)
                        violationOut['file'] = file
                        violationOut['lineNumbers'] = str(lineNumber)

                        data.append(violationOut)
                        dedup[dedupKey] = violationOut

        del dedup

        cls.logger.info("Num results: %d", len(data))

        writer = csv.DictWriter(
            output,
            extrasaction='ignore',
            fieldnames=[
                "name",
                "description",
                "violation",
                "effort",
                "category",
                "labels",
                "file",
                "lineNumbers",
                "false positive",
                "explanation"
            ],
        )
        if header:
            writer.writeheader()
        writer.writerows(data)
        output = output.getvalue()

        cls.logger.info("Done Converting MTA Results to CSV.")
        return output

    @classmethod
    def processMtaResultsFiles(cls, mtaFile:str, outFile:str="-", header=True):
        cls.logger.info("Processing MTA Results.")

        output = cls.__readMtaResults(mtaFile)
        output = cls.__mtaToCsv(output, header)

        if outFile == "-":
            cls.logger.info("Writing to stdout.")
            print(output)
        else:
            cls.logger.info("Writing to file: %s", outFile)
            with open(outFile, "w") as outFileFd:
                outFileFd.write(output)
            print(outFile)
        cls.logger.info("Done processing MTA Results.")

    @classmethod
    def processFromArgs(cls, args):
        """
        Route to call from argparse arguments.
        :param args:
        :return:
        """
        cls.logger.info("Processing from args.")

        try:
            cls.processMtaResultsFiles(
                mtaFile=args.mtaFile,
                outFile=args.outFile,
                header=not args.noHeader,
            )
        except Exception as e:
            cls.logger.exception("FAILED to process dependency trees: ")
            print(
                "FAILED to process dependency trees. See log for more details. Error: ",
                e,
                file=sys.stderr
            )
            exit(2)

    @classmethod
    def setupArgParse(cls, argParserSubcommands) -> None:
        recurseParser = argParserSubcommands.add_parser("mtaResultToCsv", help="Just run MTA results to csv.")

        recurseParser.add_argument("mtaFile", help="MTA results yaml file to process. '-' to get from stdin.").completer=argcomplete.completers.FilesCompleter()
        recurseParser.add_argument("--outFile", dest="outFile", nargs="?", default="-", help="File to output to. '-'(default) to output from stdout.").completer=argcomplete.completers.FilesCompleter()
        recurseParser.add_argument("--noHeader", dest="noHeader", action="store_true", help="If this should not add csv headers to the resulting CSV document.")

        recurseParser.set_defaults(func=cls.processFromArgs)


class DepTreeCollator:
    """
    Class to encapsulate code to collate dependency tree outputs.

    "Main" method is "process"
    """
    logger = logging.getLogger("DepTreeCollator")

    @classmethod
    def __readTreeFiles(cls, fileName: str, directory: str = ".") -> dict:
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
    def __processChild(cls, output: dict, file: str, child: dict) -> None:
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
                cls.__processChild(output, file, curSubChild)

    @classmethod
    def __collateDeps(cls, depTrees: dict) -> dict:
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
                    cls.__processChild(output, curFile, curSubChild)
            else:
                cls.logger.info("File had no dependencies.")
        # sort results
        output = dict(sorted(output.items()))

        cls.logger.info("Done collating dependency trees. # unique dependencies: %s", len(output))
        return output

    @classmethod
    def __outputResult(cls, deps, outFile: str, outFormat: str = "-") -> None:
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
    def process(cls, fileName: str = "depTree.json", directory: str = ".", outFile: str | None = None,
                outFormat: str = "-") -> dict:
        """
        Processes a directory for their dependencies. Collates them into an organized dict of individual, unique dependencies.

        :param directory: The directory to search. Defaults to current working directory.
        :param fileName: The name of the dependency tree output files in th directory.
        :param outFile:
        :param outFormat:
        :return:
        """
        cls.logger.info("Processing dependency tree.")

        deps = cls.__readTreeFiles(fileName, directory=directory)
        deps = cls.__collateDeps(deps)
        if outFile is not None:
            cls.__outputResult(deps, outFile, outFormat)

        cls.logger.info("Done processing dependency tree.")
        return deps

    @classmethod
    def processFromArgs(cls, args):
        """
        Route to call from argparse arguments.
        :param args:
        :return:
        """
        cls.logger.info("Processing from args.")

        try:
            cls.process(
                fileName=args.inFileName,
                directory=args.directory,
                outFile=args.outFile,
                outFormat=args.outFormat,
            )
        except Exception as e:
            cls.logger.exception("FAILED to process dependency trees: ")
            print(
                "FAILED to process dependency trees. See log for more details. Error: ",
                e,
                file=sys.stderr
            )
            exit(2)

    @classmethod
    def setupArgParse(cls, argParserSubcommands) -> None:
        recurseParser = argParserSubcommands.add_parser("depTreeCollate", help="Just run dependency tree collation.")

        recurseParser.add_argument("--directory", dest="directory", nargs="?", default=".",
                                   help="The directory to search for dep tree files in. Defaults to current directory '.'.")
        recurseParser.add_argument("--inFileName", dest="inFileName", nargs="?", default="depTree.json",
                                   help="The file name to search form. Expects JSON files only. Defaults to 'depTree.json'.")
        recurseParser.add_argument("--outFormat", dest="outFormat", nargs="?", default="-",
                                   help="The format to output with. Accepts '-' (default, determines based on file extension of out file), 'json', or 'csv'")
        recurseParser.add_argument("--outFile", dest="outFile", nargs="?", default="-",
                                   help="The file to output to. '-'(default) to output to stdout.")

        recurseParser.set_defaults(func=cls.processFromArgs)


class GitPuller:
    logger = logging.getLogger("GitPuller")


class RecMta:
    logger = logging.getLogger("RecMta")

    @classmethod
    def doRecurseFromArgs(cls, args):
        cls.logger.info("Starting recursive process.")

    @classmethod
    def setupArgParse(cls, argParserSubcommands) -> None:
        recurseParser = argParserSubcommands.add_parser("recurse", help="Run full recursive MTA runner.")

        recurseParser.set_defaults(func=cls.doRecurseFromArgs)


argParser = argparse.ArgumentParser(
    # prog='mta2',
    description='Recursive MTA Runner',
)
subCommands = argParser.add_subparsers(dest='command', help='Subcommands')

MtaResultToCsv.setupArgParse(subCommands)
DepTreeCollator.setupArgParse(subCommands)
RecMta.setupArgParse(subCommands)

argcomplete.autocomplete(argParser)
args = argParser.parse_args()


if hasattr(args, "func"):
    args.func(args)
else:
    print("ERROR: No command specified.", file=sys.stderr)
    argParser.print_help()
