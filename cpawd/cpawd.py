"""

Implements the command line interface for the ComputePods Async based
Watch-Do tool.

"""

import argparse
import asyncio
import logging
import signal

from .loadConfiguration import loadConfig
from .taskRunner import runTasks, shutdownTasks

def cpawd() :
  """

  Parse the command line arguments, load the configuration, and then run
  the tasks using the `asyncio.run` method.

  """


  argparser = argparse.ArgumentParser(
    description="Asynchronously watch multiple directories and perform actions on changes."
  )
  argparser.add_argument("-c", "--config", action='append',
    default=[], help="overlay configuration from file"
  )
  argparser.add_argument("-v", "--verbose", default=False,
    action=argparse.BooleanOptionalAction,
    help="show the loaded configuration"
  )
  argparser.add_argument("-d", "--debug", default=False,
    action=argparse.BooleanOptionalAction,
    help="provide debugging output"
  )
  cliArgs = argparser.parse_args()

  if cliArgs.debug :
    logging.basicConfig(level=logging.DEBUG)
  else :
    logging.basicConfig(level=logging.WARNING)

  logger = logging.getLogger("taskRunner")

  config = loadConfig(cliArgs)

  loop = asyncio.get_event_loop()

  def signalHandler(signum) :
    """
    Handle an OS system signal by stopping the debouncing tasks

    """
    print("")
    print("Shutting down...")
    logger.info("SignalHandler: Caught signal {}".format(signum))
    shutdownTasks.set()

  loop.set_debug(cliArgs.verbose)
  loop.add_signal_handler(signal.SIGTERM, signalHandler, "SIGTERM")
  loop.add_signal_handler(signal.SIGHUP,  signalHandler, "SIGHUP")
  loop.add_signal_handler(signal.SIGINT,  signalHandler, "SIGINT")
  loop.run_until_complete(runTasks(config))

  print("\ndone!")
