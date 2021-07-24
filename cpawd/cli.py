# This is the ComputePods Async based Watch-Do tool

import argparse
import asyncio

from .loadConfiguration import loadConfig
from .taskRunner import runTasks

argparser = argparse.ArgumentParser(
  description="Asynchronously watch multiple directories and perform actions on changes."
)
argparser.add_argument("-c", "--config", action='append',
  default=[], help="overlay configuration from file"
)
argparser.add_argument("-v", "--verbose", default=False,
  action=argparse.BooleanOptionalAction,
  help="provide more detailed output"
)
cliArgs = argparser.parse_args()

def cli() :
  config = loadConfig(cliArgs)

  try :
    asyncio.run(runTasks(config))
  except KeyboardInterrupt :
    print("\ndone!")
