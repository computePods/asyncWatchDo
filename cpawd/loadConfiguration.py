"""
Load and normalise the cpawd configuration

"""

import aiofiles
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

def taskError(message, aTask) :
  print("ERROR:")
  print(message)
  print("---------------------------------------------------------")
  print(yaml.dump(aTask))
  print("---------------------------------------------------------")
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

  if cliArgs.debug :
    config['debug'] = cliArgs.debug

  unLoadedConfig = cliArgs.config.copy()
  unLoadedConfig.insert(0,'cpawdConfig.yaml')
  while 0 < len(unLoadedConfig) :
    aConfigPath = unLoadedConfig[0]
    del unLoadedConfig[0]
    if os.path.exists(aConfigPath) :
      try :
        with open(aConfigPath) as aConfigFile :
          aConfig = yaml.safe_load(aConfigFile.read())
          mergeYamlData(config, aConfig, "")
        if 'include' in config :
          unLoadedConfig.extend(config['include'])
          del config['include']
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
      taskError(
        "the projectDir for task {} MUST exist in the file system".format(aTaskName),
        aTask
      )

    if 'watch' not in aTask or not aTask['watch'] :
      if 'runOnce' in aTask :
        aTask['watch'] = []
      else :
        taskError("all tasks, which are not runOnce, MUST have a collection of files/directories to watch\nno 'watch' list provided in task [{}]:".format(aTaskName), aTask)
    expandedWatches = []
    for aWatch in aTask['watch'] :
      newWatch = os.path.expanduser(aWatch)
      if not newWatch.startswith('/') :
        newWatch = os.path.join(aTask['projectDir'], newWatch)
        os.makedirs(newWatch, exist_ok=True)
      expandedWatches.append(newWatch)
    aTask['watch'] = expandedWatches

  # expand toolTips and commands
  for aTaskName, aTask in config['tasks'].items() :
    if 'cmd' not in aTask :
      taskError("all tasks MUST have a cmd; no cmd provied in task [{}]".format(aTaskName), aTask)
    if type(aTask['cmd']) is not list :
      taskError("task cmds MUST be a list of command followed by arguments\nfound type: {} in task {}".format(type(aTask['cmd']), aTaskName), aTask)
    try :
      newCmd = []
      for anArgument in aTask['cmd'] :
        newCmd.append(anArgument.format(**config['tasks']))
      aTask['cmd'] = newCmd
    except Exception as err :
      print("Could not expand variables in cmd string:")
      print(yaml.dump(aTask['cmd']))
      print(repr(err))

    if 'toolTips' in aTask :
      try :
        aTask['toolTips'] = aTask['toolTips'].format(**config['tasks'])
      except Exception as err :
        print("Could not expand variables in toolTips string:")
        print(yaml.dump(aTask['toolTips']))
        print(repr(err))

  if config['verbose'] :
    print("configuration:")
    print("---------------------------------------------------------------")
    print(yaml.dump(config))

  # announce User Messages
  print("---------------------------------------------------------------")
  print("\nTool tips:\n")
  for aTaskName, aTask in config['tasks'].items() :
    if 'toolTips' in aTask :
      print("{}\n  {}".format(aTaskName, aTask['toolTips']))

  # announce log files
  print("\n---------------------------------------------------------------")
  print("\nLogfiles for each task:\n")
  for aTaskName, aTask in config['tasks'].items() :
    print("{}\n  tail -f {}".format(aTaskName, aTask['logFilePath']))
    print("  {} {}".format(cliArgs.pager, aTask['logFilePath']))
  print("")
  print("---------------------------------------------------------------")
  print("")

  return config