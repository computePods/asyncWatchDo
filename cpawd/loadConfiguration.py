"""
Load and normalise the cpawd configuration

"""

import os
import shutil
import sys
import time
import traceback
import yaml

def mergeYamlData(yamlData, newYamlData, thePath) :
  """

  This is a generic Python merge. It is a *deep* merge and handles both
  dictionaries and arrays

  """

  if type(yamlData) is None :
    print("ERROR yamlData should NEVER be None ")
    sys.exit(-1)

  if type(yamlData) != type(newYamlData) :
    print("Incompatible types {} and {} while trying to merge YAML data at {}".format(type(yamlData), type(newYamlData), thePath))
    print("Stoping merge at {}".format(thePath))
    return

  if type(yamlData) is dict :
    for key, value in newYamlData.items() :
      if key not in yamlData :
        yamlData[key] = value
      elif type(yamlData[key]) is dict :
        mergeYamlData(yamlData[key], value, thePath+'.'+key)
      elif type(yamlData[key]) is list :
        for aValue in value :
          yamlData[key].append(aValue)
      else :
        yamlData[key] = value
  elif type(yamlData) is list :
    for value in newYamlData :
      yamlData.append(value)
  else :
    print("ERROR yamlData MUST be either a dictionary or an array.")
    sys.exit(-1)

def loadConfig(cliArgs) :
  """

  Load the configuration by merging any `cpawdConfig.yaml` found in the
  current working directory, and then any other configuration files
  specified on the command line.

  Then perform the following normalisation:

  - The base working directory is computed using the `baseDir` and
  `prefix` keys found in the `workDir` section of the merged
  configuration.

  - Compute `workDir` for each task in the `tasks` section of the merged
  configuration.

  - Ensure all `workDir` exists (both for the base and the individual
  tasks)

  - Expand all watched paths to an absolute path in the file system.

  - Check that the `projectDir` exists for each task.

  - Compute logFilePaths and open logFiles for each task.

  """

  config = {
    'workDir' : {
      'baseDir' : '/tmp',
      'prefix' : 'cpawd'
    },
    'tasks' : {},
    'verbose' : False
  }

  if cliArgs.verbose :
    config['verbose'] = cliArgs.verbose

  cliArgs.config.insert(0,'cpawdConfig.yaml')
  for aConfigPath in cliArgs.config :
    if os.path.exists(aConfigPath) :
      try :
        with open(aConfigPath) as aConfigFile :
          aConfig = yaml.safe_load(aConfigFile.read())
          mergeYamlData(config, aConfig, "")
      except Exception as err :
        print("Could not load configuration from [{}]".format(aConfigPath))
        print(err)

  # create the working directory
  if 'workDir' not in config['workDir'] :
    config['workDir']['workDir'] = os.path.join(
      config['workDir']['baseDir'],
      config['workDir']['prefix'] + '-' + time.strftime("%Y%m%d-%H%M%S")
    )

  workDir = config['workDir']['workDir']

  if os.path.exists(workDir) :
    shutil.rmtree(workDir)
  os.makedirs(workDir)

  # ensure the task work and project directories exist
  for aTaskName, aTask in config['tasks'].items() :
    aTask['workDir'] = os.path.join(workDir, aTaskName)
    os.makedirs(aTask['workDir'])
    aTask['logFilePath'] = os.path.join(workDir, aTaskName, 'command.log')
    if 'projectDir' in aTask :
      aTask['projectDir'] = os.path.abspath(os.path.expanduser(aTask['projectDir']))
    else:
      aTask['projectDir'] = aTask['workDir']

    if not os.path.exists(aTask['projectDir']) :
      print("ERROR: the projectDir for task {} MUST exist in the file system".format(aTaskName))
      print("---------------------------------------------------------")
      print(yaml.dump(aTask))
      print("---------------------------------------------------------")
      sys.exit(-1)

    if 'watch' not in aTask or not aTask['watch'] :
      print("ERROR: all tasks MUST have a collection of files/directories to watch")
      print("       no 'watch' list provided in task [{}]:".format(aTaskName))
      print("---------------------------------------------------------")
      print(yaml.dump(aTask))
      print("---------------------------------------------------------")
      sys.exit(-1)
    expandedWatches = []
    for aWatch in aTask['watch'] :
      newWatch = os.path.expanduser(aWatch)
      if not newWatch.startswith('/') :
        newWatch = os.path.join(aTask['projectDir'], newWatch)
      expandedWatches.append(newWatch)
    aTask['watch'] = expandedWatches

  # expand commands and open logFiles
  for aTaskName, aTask in config['tasks'].items() :
    try :
      aTask['cmd'] = aTask['cmd'].format(**config['tasks'])
    except Exception as err :
      print("Could not expand variables in cmd string:")
      print(aTask['cmd'])
      print(repr(err))

  if config['verbose'] :
    print("configuration:")
    print("---------------------------------------------------------------")
    print(yaml.dump(config))
    print("---------------------------------------------------------------")

  # open log files
  print("\nLogfiles for each task:")
  for aTaskName, aTask in config['tasks'].items() :
    aTask['logFile'] = open(aTask['logFilePath'], 'w')
    print("{}\n  tail -f {}".format(aTaskName, aTask['logFilePath']))
  print("")
  print("---------------------------------------------------------------")
  print("")

  return config