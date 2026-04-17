#!/bin/python
#
# Recursive RHMTA runner
#
# Requirements:
#  - argparse
#  - argcomplete
#  - PyYaml
#  - GitPython
#

import os
import re
import subprocess
import time
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
import shutil

from git import Repo

logging.basicConfig(
    filename='mta2.log',
    filemode='w',
    format='[%(asctime)s][%(name)-15s][%(levelname)-5s] %(message)s',  # Use %(name)s
    level=logging.DEBUG
)


class InvalidInputException(ValueError):
    """Raised when there is an invalid input given"""
    pass


class CmdFailedException(Exception):
    """Raised when a subcommand process fails"""
    pass


class Utils:
    logger = logging.getLogger("Utils")

    @classmethod
    def alertBell(cls, num: int = 1, spacingSecs: float | bool = False) -> None:
        """
        Sends a bell signal to stdout.
        :param num: The number of times to send the bell
        :param spacingSecs: The timing between the bell sounds
        :return:
        """
        cls.logger.info("Sending bell alert %d/%s", num, spacingSecs)
        for i in range(num):
            sys.stdout.write('\a')
            sys.stdout.flush()
            if spacingSecs:
                time.sleep(spacingSecs)
        cls.logger.debug("Done sending bell alert.")

    @classmethod
    def alertUser(cls) -> None:
        """
        Sends a standard "User alert" sound.
        :return:
        """
        cls.alertBell(5, 0.5)

    @classmethod
    def writeBar(cls, character):
        size = shutil.get_terminal_size()
        print(character * size.columns)

    @classmethod
    def getBoolInput(cls, prompt):
        """
        Prompts the user for input and validates it as a boolean (Y/N).

        Args:
            prompt: The message to display to the user.

        Returns:
            True if the user enters 'yes' or 'y', False if 'no' or 'n'.
        """
        while True:
            user_input = input(
                f"{prompt} [Y/N]: ").strip().lower()  # Get input, remove leading/trailing spaces, and convert to lowercase

            if user_input in ('yes', 'y'):
                return True
            elif user_input in ('no', 'n'):
                return False
            else:
                print("Invalid input. Please enter 'yes'/'y' or 'no'/'n'.")

    @classmethod
    def getStringInput(cls, prompt):
        """
        Prompts the user for input and validates it as a boolean (Y/N).

        Args:
            prompt: The message to display to the user.

        Returns:
            True if the user enters 'yes' or 'y', False if 'no' or 'n'.
        """
        while True:
            user_input = input(f"{prompt}: ").strip()  # Get input, remove leading/trailing spaces
            return user_input

    @classmethod
    def getChoiceInput(cls, prompt: str, choices: list[str]):
        choiceStr = ""

        for index, choice in enumerate(choices):
            if choiceStr != "":
                choiceStr += ", "
            choiceStr += f"({index + 1}){choice}"

        while True:
            userChoice = input(prompt + " Choose one: [" + choiceStr + "]: ").strip()

            for index, choice in enumerate(choices):
                if userChoice == choice or userChoice == str(index + 1):
                    cls.logger.info("User chose %s out of %s", choice, choices)
                    return choice
            print("Invalid input, please try again. Must choose from given choices.")


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
                "description": curResult.get("description", "")
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
                    # dedup key to reference a single file with this particular violation
                    dedupKey = violation["name"] + violation['violation'] + file

                    if dedupKey in dedup.keys():
                        dedup[dedupKey]['lineNumbers'] += "," + str(lineNumber)
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
    def processMtaResultsFiles(cls, mtaFile: str, outFile: str = "-", header=True):
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
            cls.logger.exception("FAILED to MTA results: ")
            print(
                "FAILED to MTA results. See log for more details. Error: ",
                e,
                file=sys.stderr
            )
            exit(2)

    @classmethod
    def setupArgParse(cls, argParserSubcommands) -> None:
        recurseParser = argParserSubcommands.add_parser("mtaResultToCsv", help="Just run MTA results to csv.")

        recurseParser.add_argument("mtaFile",
                                   help="MTA results yaml file to process. '-' to get from stdin.").completer = argcomplete.completers.FilesCompleter()
        recurseParser.add_argument("--outFile", dest="outFile", nargs="?", default="-",
                                   help="File to output to. '-'(default) to output from stdout.").completer = argcomplete.completers.FilesCompleter()
        recurseParser.add_argument("--noHeader", dest="noHeader", action="store_true",
                                   help="If this should not add csv headers to the resulting CSV document.")

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
            raise InvalidInputException("No dependency tree files found.")

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
            if outFile.endswith(".json") or outFile == "-":
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
            raise InvalidInputException("Unknown output format: " + outFormat)

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
    def filterDeps(cls, deps: dict, depRegex: re.Pattern = None) -> dict:
        if filter is None:
            return deps
        return {k: v for k, v in deps.items() if re.search(depRegex, k)}

    @classmethod
    def process(
            cls,
            fileName: str = "depTree.json",
            directory: str = ".",
            outFile: str | None = None,
            outFormat: str = "-",
            depRegex: re.Pattern = None
    ) -> dict:
        """
        Processes a directory for their dependencies. Collates them into an organized dict of individual, unique dependencies.

        :param directory: The directory to search. Defaults to current working directory.
        :param fileName: The name of the dependency tree output files in th directory.
        :param outFile:
        :param outFormat:
        :param depRegex:
        :return: The dict of dependencies used by this project
        """
        cls.logger.info("Processing dependency tree.")



        deps = cls.__readTreeFiles(fileName, directory=directory)
        deps = cls.__collateDeps(deps)
        deps = cls.filterDeps(deps, depRegex)
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


class CommandUtils:
    logger = logging.getLogger("CommandUtils")

    @classmethod
    def runCommand(
            cls,
            command: list[str],
            outputDir: str,
            runDir: str = "."
    ) -> subprocess.CompletedProcess:
        cls.logger.info("Running command: %s", command[0])
        cls.logger.debug("Full command: %s", command)
        initialD = os.getcwd()

        outputFilePrefix = os.path.basename(command[0])
        outputFilePrefix = os.path.join(outputDir, outputFilePrefix)

        stdOutFile = outputFilePrefix + ".stdout.log"
        stdErrFile = outputFilePrefix + ".stderr.log"

        cls.logger.debug("Stdout going to file: %s", stdOutFile)
        cls.logger.debug("Stderr going to file: %s", stdErrFile)

        result = None
        try:
            os.chdir(runDir)
            cls.logger.debug("Running command in %s", os.getcwd())

            with open(stdOutFile, "w") as outFileD, open(stdErrFile, "w") as errFileD:
                startTime = time.perf_counter()
                result = subprocess.run(
                    command,
                    stdout=outFileD,
                    stderr=errFileD,
                    shell=False,
                    text=True,
                    check=False,
                )
                endTime = time.perf_counter()
                cls.logger.debug("Command finished in %s", endTime - startTime)
        finally:
            os.chdir(initialD)

        if result.returncode != 0:
            raise CmdFailedException(
                "FAILED to run command: " + command[0] +
                ", exited with " + str(result.returncode) +
                "  Output sent to logs in " + outputDir
            )
        return result


class MvnUtils:
    logger = logging.getLogger("MtaRunner")

    @classmethod
    def runDepTree(
            cls,
            projectDir: str,
            outputDir: str,
            depTreeMvnCmd: str = "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree"
    ):
        cls.logger.info("Running Mvn dependency tree for project %s", projectDir)
        CommandUtils.runCommand(
            [
                "mvn", depTreeMvnCmd,
                "-DoutputFile=depTree.json", "-DoutputType=json"
            ],
            outputDir,
            projectDir
        )
        cls.logger.info("Done running Mvn dependency tree for project %s", projectDir)


class MtaRunner:
    logger = logging.getLogger("MtaRunner")

    @classmethod
    def getMtaReportDir(cls, outputDir: str):
        return os.path.join(outputDir, "report")

    @classmethod
    def runMta(
            cls,
            mtaLocation: str,
            projectLocation: str,
            outputDir: str,
            mtaArgs: list[str],
            mtaIncidentSelect: str = None
    ):
        cls.logger.info("Running Mta on project %s", projectLocation)
        print("Running Mta on project (this can take some time): " + projectLocation)

        mtaResultsDir = cls.getMtaReportDir(outputDir)

        commandList = [
            "./mta-cli",
            "analyze",
            "--input", projectLocation,
            "--output", mtaResultsDir,
            "--no-cleanup",
            "--mode", "source-only",
        ]
        if mtaIncidentSelect:
            commandList.append("--incident-selector")
            commandList.append(mtaIncidentSelect)
        commandList += mtaArgs

        CommandUtils.runCommand(commandList, outputDir, mtaLocation)

        cls.logger.info("Finished running mta.")
        return mtaResultsDir

    @classmethod
    def mtaArgsToList(cls, mtaArgs: str) -> list[str]:
        return mtaArgs.split()


class GitPuller:
    logger = logging.getLogger("GitPuller")
    depsProcessedInRun = []

    @classmethod
    def initGitDepMap(cls, gitMapFileName:str):
        cls.logger.info("Initializing git dependency map.")

        if os.path.exists(gitMapFileName):
            cls.logger.debug("Git dependency map already exists.")
            return

        with open(gitMapFileName, "w") as gitMapFile:
            gitMapFile.write("{}")
        cls.logger.info("Initialized new git dependency map.")

    @classmethod
    def readGitDepMap(cls, gitMapFileName):
        cls.logger.debug("Reading git dependency map.")
        with open(gitMapFileName, 'r') as file:
            return json.load(file)

    @classmethod
    def saveGitDepMap(cls, gitMapFileName, depMap: dict):
        cls.logger.debug("Saving git dependency map to file.")
        with open(gitMapFileName, 'w') as file:
            return json.dump(depMap, file, indent=4)

    @classmethod
    def haveGitInfoForDep(cls, gitMapFileName, dep):
        cls.logger.debug("Checking for git.")
        return dep in cls.readGitDepMap(gitMapFileName)

    @classmethod
    def ensureDepEntryExists(cls, gitMapFileName, dep) -> dict:
        gitDepMap = cls.readGitDepMap(gitMapFileName)

        if dep in cls.readGitDepMap(gitMapFileName):
            return gitDepMap
        gitDepMap[dep] = {
            "type": "skip"
        }
        cls.saveGitDepMap(gitMapFileName, gitDepMap)
        return gitDepMap

    @classmethod
    def setSkipDep(cls, gitMapFileName, dep):
        cls.logger.debug("Setting skip flag for git dependency.")
        gitDepMap = cls.ensureDepEntryExists(gitMapFileName, dep)

        gitDepMap[dep]["type"] = "skip"
        cls.saveGitDepMap(gitMapFileName, gitDepMap)

    @classmethod
    def checkGetDepGitInfo(cls, gitMapFileName, dependencies: dict):
        cls.logger.debug("Checking for git dependency info. Getting git info from user if not existent.")
        depList = list(dependencies.keys())

        firstNotFound = True

        for curDep in depList:

            if curDep in cls.depsProcessedInRun:
                cls.logger.info("Skipping dependency %s due to already processed it in this run.", curDep)
                continue

            if firstNotFound:
                firstNotFound = False
                print()
                Utils.writeBar("=")
                Utils.writeBar("=")
                print()
                print("Need to get some dependency git locations from you;")
                Utils.alertUser()
                print()
                Utils.writeBar("-")
                print()
            else:
                print()
                Utils.writeBar("-")
                print()

            cls.logger.info("Checking git dependency info for dependency: %s", curDep)
            gitDepMap = cls.ensureDepEntryExists(gitMapFileName, curDep)

            print("Dependency: " + curDep)

            print("\tFound in:")
            for curDepFile in dependencies[curDep]['files']:
                print("\t\t" + curDepFile)
            print()

            if cls.haveGitInfoForDep(gitMapFileName, curDep):
                cls.logger.info("Had git dependency info for dependency: %s / %s", curDep, gitDepMap[curDep])

                print("Git setup for dependency already defined. Info:")
                for curKey, curValue in gitDepMap[curDep].items():
                    print("\t" + curKey + " = " + curValue)
                print()

                if not Utils.getBoolInput("Git setup for " + curDep + " already specified. Would you like to modify?"):
                    cls.logger.info("User chose to not modify git setup for dependency: %s", curDep)
                    cls.depsProcessedInRun.append(curDep)
                    continue
            else:
                cls.logger.info("Did not have git dependency info. Getting from user")

            gitDepMap[curDep]["type"] = Utils.getChoiceInput("How should this script access this project?",
                                                             ["clone", "localDir", "skip"])

            if gitDepMap[curDep]["type"] == "skip":
                cls.logger.info("User chose to skip dependency: %s", curDep)
            elif gitDepMap[curDep]["type"] == "clone":
                gitDepMap[curDep]["repo"] = Utils.getStringInput("Enter the git repo url")
                gitDepMap[curDep]["checkout"] = Utils.getStringInput("Enter the branch/ checkout name to use (blank to use default branch)")
                gitDepMap[curDep]["subDir"] = Utils.getStringInput("Enter the sub directory in the repo the project is placed in (blank for project root)")
            elif gitDepMap[curDep]["type"] == "localDir":
                gitDepMap[curDep]["localDir"] = Utils.getStringInput("Enter the local directory where the code exists")
                gitDepMap[curDep]["checkout"] = Utils.getStringInput("Enter the branch/ checkout name to use (blank to not checkout)")

            cls.logger.info("Got dependency info from user: %s -> %s", curDep, gitDepMap[curDep])
            # gitDepMap[curDep]["repo"] = Utils.getStringInput("Enter the git repo url")
            cls.saveGitDepMap(gitMapFileName, gitDepMap)
            cls.depsProcessedInRun.append(curDep)

        cls.logger.info("Finished getting git dependency info from user.")
        print("Completed getting this round of dependency info.")

    @classmethod
    def setupDepDir(cls, gitMapFileName, dep, pullDir="./") -> str:
        cls.logger.info("Checking out dependency: %s", dep)

        depDir = os.path.join(pullDir, dep)

        depInfo = cls.readGitDepMap(gitMapFileName)[dep]

        if depInfo["type"] == "clone":
            cls.logger.info("Clone dependency: %s", dep)
            repo = Repo.clone_from(depInfo["type"]["repo"], depDir)

            if depInfo["checkout"]:
                repo.git.checkout("HEAD", b=depInfo["checkout"])
            depDir = repo.working_tree_dir

            if depInfo["subDir"]:
                depDir = os.path.join(depDir, depInfo["subDir"])

        elif depInfo["type"] == "localDir":
            cls.logger.info("Using existing local dependency source: %s", dep)
            depDir = depInfo["localDir"]
            if depInfo["checkout"]:
                repo = Repo(depDir)
                repo.git.checkout("HEAD", b=depInfo["checkout"])

        cls.logger.debug("Resulting dir to analyze: %s", depDir)
        return depDir


class ProjectAnalysis:
    logger = logging.getLogger("ProjectAnalysis")

    @classmethod
    def analyzeProject(
            cls,
            mtaLocation: str,
            mtaArgs: list[str],
            projectLocation: str,
            outputDir: str,
            depRegex: re.Pattern = None,
            mtaIncidentSelect: str = None
    ) -> dict:
        cls.logger.info("Analyzing project: %s", projectLocation)
        startTime = time.perf_counter()

        mtaResultsDir = os.path.join(outputDir, "mtaResults")

        if os.path.exists(mtaResultsDir):
            cls.logger.info("Output directory already exists: %s", mtaResultsDir)
            choice = Utils.getChoiceInput(
                "Output directory already exists (" + mtaResultsDir + ") What should we do?",
                ["overwrite", "use", "cancel"]
            )
            if choice == "overwrite":
                cls.logger.info("Overwriting mta results directory: %s", mtaResultsDir)
                shutil.rmtree(mtaResultsDir)
            elif choice == "use":
                cls.logger.info("Using previously generated mta results directory: %s", mtaResultsDir)

        mtaReportDir = MtaRunner.getMtaReportDir(mtaResultsDir)
        depsFile = os.path.join(outputDir, "dependencies.json")
        dependencies = {}

        if not os.path.exists(mtaResultsDir):
            cls.logger.info("Processing new project.")
            Path(mtaResultsDir).mkdir(parents=True, exist_ok=True)

            MtaRunner.runMta(
                mtaLocation,
                projectLocation,
                mtaResultsDir,
                mtaArgs,
                mtaIncidentSelect=mtaIncidentSelect
            )

            MtaResultToCsv.processMtaResultsFiles(
                os.path.join(mtaReportDir, "output.yaml"),
                os.path.join(mtaReportDir, "results.csv")
            )

            MvnUtils.runDepTree(projectLocation, outputDir)

            dependencies = DepTreeCollator.process(
                directory=projectLocation,
                outFile=depsFile,
                depRegex=depRegex
            )
        else:
            cls.logger.info("Getting results from old mta run.")
            with open(depsFile, "r") as f:
                dependencies = json.load(f)
                dependencies = DepTreeCollator.filterDeps(dependencies, depRegex)

        endTime = time.perf_counter()
        cls.logger.info("Done analyzing project: %s", projectLocation)
        cls.logger.info("Analyzed project in %d seconds", endTime - startTime)
        return dependencies


class RecMta:
    logger = logging.getLogger("RecMta")

    @classmethod
    def __updateDepLists(cls, depsToAnalyze: list, depsAnalyzed: set, newDeps, curDep: str):
        depsAnalyzed.add(curDep)
        for curNewDep in newDeps.keys():
            if curNewDep not in depsAnalyzed:
                depsToAnalyze.append(curNewDep)

    @classmethod
    def doRecursiveProjectAnalysis(
            cls,
            mtaLocation: str,
            mtaArgs: str,
            startProject: str,
            outputDir: str = "./mta2AnalysisResults",
            projectGitMap: str = "./mta2ProjectGitMap.json",
            finishedSetFile: str = "./finishedProjects.json",
            pullLocation: str = "./mta2PulledProjects",
            cleanupPulled: bool = False,
            overwrite: bool = False,
            depRegex: re.Pattern = None,
            depsMode: str = "decompile",
            mtaIncidentSelect: str = None,
    ):
        # convert to use only absolute paths
        mtaLocation = os.path.abspath(mtaLocation)
        startProject = os.path.abspath(startProject)
        outputDir = os.path.abspath(outputDir)
        projectGitMap = os.path.abspath(projectGitMap)
        pullLocation = os.path.abspath(pullLocation)
        mtaArgs = MtaRunner.mtaArgsToList(mtaArgs)

        if depRegex is not None:
            depRegex = re.compile(depRegex)

        cls.logger.info("Starting MTA recursive project analysis.")
        cls.logger.info("\tMTA location: %s", mtaLocation)
        cls.logger.info("\tStarting project location: %s", startProject)
        cls.logger.info("\tOutput Directory: %s", outputDir)
        cls.logger.info("\tProject git map: %s", projectGitMap)
        cls.logger.info("\tProject pulling location: %s", pullLocation)
        cls.logger.info("\tCleanup pulled projects?: %s", cleanupPulled)

        if os.path.exists(outputDir):
            cls.logger.info("\tOutput directory exists: %s", outputDir)
            if overwrite:
                cls.logger.info("Deleting output directory: %s", outputDir)
                shutil.rmtree(outputDir)
            else:
                cls.logger.info("Output directory exists. Will prompt for each output directory.")

                if Utils.getBoolInput("Output directory exists. Delete before continuing?"):
                    cls.logger.info("Deleting output directory: %s", outputDir)
                    shutil.rmtree(outputDir)
                # cls.logger.error("Output directory exists, not directed to overwrite.")
                # print("Output directory already exists. Please remove before continuing. Specify '--overwrite' to automatically delete the previous results.", file=sys.stderr)
                # exit(1)

        # check inputs, create if necessary
        Path(outputDir).mkdir(parents=True, exist_ok=True)
        Path(pullLocation).mkdir(parents=True, exist_ok=True)

        GitPuller.initGitDepMap(projectGitMap)

        # initial project analysis
        print("Processing initial project: " + startProject)
        projectOutput = os.path.join(outputDir, Path(startProject).name)
        Path(projectOutput).mkdir(parents=True, exist_ok=True)

        projectDeps = ProjectAnalysis.analyzeProject(
            mtaLocation,
            mtaArgs,
            startProject,
            projectOutput,
            depRegex=depRegex,
            mtaIncidentSelect=mtaIncidentSelect
        )
        cls.logger.info("Finished initial project analysis.")
        cls.logger.debug("Initial project dependencies: %s", projectDeps)

        # deps object keys are the deps to care about
        depsToAnalyze = list(projectDeps.keys())
        depsAnalyzed = set()

        if depsMode == "decompile":
            cls.logger.info("Processing deps by MTA's decompilation functionality.")

            if os.path.exists(finishedSetFile):
                with open(finishedSetFile, 'r') as f:
                    depsAnalyzed = set(json.load(f))


            while len(depsToAnalyze) != 0:
                curDep = depsToAnalyze.pop()

                cls.logger.info("Processing dependency: %s", curDep)
                cls.logger.info("Num Dependencies left to proces: %s", len(depsToAnalyze))
                cls.logger.debug("Dependencies left to proces: %s", depsToAnalyze)

                depOutputDir = os.path.join(outputDir, curDep)

                curDepIncidentSelect = ""
                if mtaIncidentSelect:
                    curDepIncidentSelect += mtaIncidentSelect + " && "

                depParts = curDep.split(":")
                curDepIncidentSelect += "package=" + depParts[0] + "." + depParts[1]

                curDepDeps = ProjectAnalysis.analyzeProject(
                    mtaLocation,
                    mtaArgs,
                    startProject,
                    depOutputDir,
                    depRegex=depRegex,
                    mtaIncidentSelect=curDepIncidentSelect
                )

                cls.__updateDepLists(depsToAnalyze, depsAnalyzed, curDepDeps, curDep)
                with open(finishedSetFile, 'w') as f:
                    json.dump(list(depsAnalyzed), f)

        elif depsMode == "pullSource":
            cls.logger.info("Processing deps by pulling project sources.")
            GitPuller.checkGetDepGitInfo(projectGitMap, projectDeps)
            while len(depsToAnalyze) != 0:
                cls.logger.info("Num Dependencies left to proces: %s", len(depsToAnalyze))
                cls.logger.debug("Dependencies left to proces: %s", depsToAnalyze)

                curDep = depsToAnalyze.pop()
                cls.logger.info("Processing dependency: %s", curDep)

                pulledProject = GitPuller.setupDepDir(curDep, pullLocation)

                projectOutput = os.path.join(outputDir, Path(curDep).name)
                Path(projectOutput).mkdir(parents=True, exist_ok=True)

                projectDeps = ProjectAnalysis.analyzeProject(
                    mtaLocation,
                    mtaArgs,
                    pulledProject,
                    projectOutput,
                    depRegex=depRegex
                )

                cls.logger.info("Finished dependency: %s", curDep)

                GitPuller.checkGetDepGitInfo(projectGitMap, projectDeps)

                cls.__updateDepLists(depsToAnalyze, depsAnalyzed, projectDeps, curDep)

        cls.logger.info("Finished MTA recursive project analysis.")

    @classmethod
    def doRecurseFromArgs(cls, args):
        cls.logger.info("Starting recursive process from args.")

        try:
            cls.doRecursiveProjectAnalysis(
                mtaLocation=args.mtaLocation,
                mtaArgs=args.mtaArgs,
                startProject=args.startProject,
                outputDir=args.outputDir,
                projectGitMap=args.projectGitMap,
                pullLocation=args.pullLocation,
                cleanupPulled=args.cleanupPulled,
                overwrite=args.overwrite,
                depRegex=args.dependencyRegex,
                depsMode=args.depsMode,
                mtaIncidentSelect=args.mtaIncidentSelect
            )
        except Exception as e:
            cls.logger.exception("FAILED to run recursive MTA analysis: %s", e)
            print("FAILED to run recursive MTA analysis: {}".format(e))

    @classmethod
    def setupArgParse(cls, argParserSubcommands) -> None:
        recurseParser = argParserSubcommands.add_parser("recurse", help="Run full recursive MTA runner.")

        recurseParser.add_argument("--startProject", dest="startProject", nargs="?", default=".",
                                   help="The directory of the project to start from. Defaults to '.'.")
        recurseParser.add_argument("--outputDir", dest="outputDir", nargs="?", default="./mta2AnalysisResults",
                                   help="The directory to output results to. Defaults to './mta2AnalysisResults'.")

        recurseParser.add_argument("--dependencyRegex", dest="dependencyRegex", nargs="?", default=None,
                                   help="A regex pattern to use to specify which dependencies to analyze.")
        recurseParser.add_argument("--projectGitMap", dest="projectGitMap", nargs="?",
                                   default="./mta2ProjectGitMap.json",
                                   help="The map of project dependencies to git locations. Defaults to './mta2ProjectGitMap.json'.")
        recurseParser.add_argument("--pullLocation", dest="pullLocation", nargs="?", default="./mta2PulledProjects",
                                   help="The directory to pull projects into. Defaults to './mta2PulledProjects'.")
        recurseParser.add_argument("--cleanPulled", dest="cleanupPulled", action="store_true",
                                   help="If this should remove pulled projects after the run is complete.")
        recurseParser.add_argument("--overwrite", dest="overwrite", action="store_true",
                                   help="If this should overwrite existing analysis (if exists).")
        recurseParser.add_argument("--depsMode", dest="depsMode", nargs="?", default="decompile",
                                   choices=["decompile", "pullSource"],
                                   help="How we should handle dependency scanning.")
        recurseParser.add_argument("--mtaIncidentSelect", dest="mtaIncidentSelect", nargs="?", default="",
                                   help="How we should handle dependency scanning.")

        recurseParser.add_argument("--mtaLocation", dest="mtaLocation",
                                   help="The directory in which the MTA tool was extracted from.")
        recurseParser.add_argument("--mtaArgs", dest="mtaArgs",
                                   help="The arguments to pass to the MTA tool when running.")

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
