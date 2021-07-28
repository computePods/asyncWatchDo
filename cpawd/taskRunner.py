"""

This cpawd.taskRunner module implements the running of all watch-do tasks.

It uses the `DebouncingTimer` to actually run the tasks after a short
timeout period. We use this short timeout to ensure the task is only run
once for any collection of changes detected at nearly the same time.

The top level `runTasks` method initiates the `asyncio.Tasks` which
represent each watch-do task.

"""

# Use psutil.pids() (returns list of pids) to check if the task's pid is
# still running.

import aiofiles
import asyncio
import logging
import signal
import time
import traceback

from .fsWatcher import FSWatcher

logger = logging.getLogger("taskRunner")

debouncingTimers = []

class DebouncingTimer:
  """

  The DebouncingTimer class implements a simple timer to ensure multiple
  file system events result in only one invocation of the task command.

  """

  def __init__(self, timeout, taskName, taskDetails, taskLog) :
    """
    Create the timer with a specific timeout and task definition.

    The taskDetails provides the command to run, the log file used to
    record command output, as well as the project directory in which to
    run the command.

    """

    self.timeout    = timeout
    self.taskName   = taskName
    self.taskCmd    = taskDetails['cmd']
    self.taskCmdStr = " ".join(taskDetails['cmd'])
    self.taskLog    = taskLog
    self.taskDir    = taskDetails['projectDir']
    self.taskFuture = None
    self.proc       = None
    debouncingTimers.append(self)

  def cancelTask(self) :
    if self.taskFuture :
      self.taskFuture.cancel()

  async def stopTaskProc(self) :
    if self.proc :
      logger.debug("Proc found for {}".format(self.taskName))
      try:
        pid = self.proc.pid
        logger.debug("Trying to terminate (SIGHUP) {} (pid:{})".format(
          self.taskName, pid
        ))
        self.proc.send_signal(signal.SIGHUP)
        logger.debug("Waiting up to 10 seconds for {} to finish (pid:{})".format(
          self.taskName, pid
        ))
        await asyncio.wait_for(self.proc.wait(), 30)
        retCode = self.proc.returncode
        logger.debug("Return code for {} is {} (pid:{})".format(
          self.taskName, retCode, pid
        ))
        taskLog = self.taskLog
        await taskLog.write("{} task ({}) exited with {}\n".format(
          self.taskName, pid, retCode
        ))
        await taskLog.write("\n")
        await taskLog.flush()
        logger.debug("Finished {} ({}) command [{}] exited with {}".format(
          self.taskName, pid, self.taskCmdStr, retCode
        ))
        self.proc = None
      except ProcessLookupError :
        logger.debug("No process found for {} (pid:{})".format(
          self.taskName, self.proc.pid
        ))
        self.proc = None
      except Exception as err:
        logger.error("Could not terminate proc {}".format(self.taskName))
        logger.error(repr(err))
        traceback.print_exc()
    else :
      logger.debug("No proc for {}".format(self.taskName))

  async def taskRunner(self) :
    """

    Run the task's command, after sleeping for the timeout period, using
    `asyncio.create_subprocess_shell` command.

    """

    try:
      await asyncio.sleep(self.timeout)

      await self.stopTaskProc()

      # Now we can run the new task...
      #
      logger.debug("Running {} command [{}]".format(
        self.taskName, self.taskCmdStr
      ))
      self.proc = await asyncio.create_subprocess_exec(
        *self.taskCmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=self.taskDir
      )
      print(f'Ran: {self.taskName}')
      stdout = self.proc.stdout
      taskLog = self.taskLog
      if stdout :
        await taskLog.write("\n============================================================================\n")
        await taskLog.write("{} ({}) stdout @ {}\n".format(
          self.taskName, self.proc.pid, time.strftime("%Y/%m/%d %H:%M:%S")
        ))
        await taskLog.write("{}\n".format(self.taskCmdStr))
        await taskLog.write("----------------------------------------------------------------------------\n")
        await taskLog.flush()
        while not stdout.at_eof() :
          logger.debug("Collecting {} stdout ({})".format(
            self.taskName, self.proc.pid
          ))
          aLine = await stdout.readline()
          await taskLog.write(aLine.decode())
          await taskLog.flush()
        logger.debug("Finshed collecting {} stdout ({})".format(
          self.taskName, self.proc.pid
        ))
        await taskLog.write("\n----------------------------------------------------------------------------\n")
        await taskLog.write("{} ({}) stdout @ {}\n".format(
          self.taskName, self.proc.pid, time.strftime("%Y/%m/%d %H:%M:%S")
        ))
        await self.stopTaskProc()
        await taskLog.flush()
    except Exception as err :
      print("Caught exception while running {} task".format(self.taskName))
      print(repr(err))

  async def reStart(self) :
    """

    (Re)Start the timer. If the timer is already started, it is restarted
    with a new timeout period.

    """
    logger.debug("Stopping {} from reStart".format(self.taskName))
    await self.stopTaskProc()
    logger.debug("Stoped {} from reStart".format(self.taskName))

    if self.taskFuture :
      logger.debug("Cancelling {} timer".format(self.taskName))
      self.taskFuture.cancel()

    logger.debug("Starting {} timer".format(self.taskName))
    self.taskFuture = asyncio.ensure_future(self.taskRunner())

async def watchDo(aTaskName, aTask) :
  """

  Setup and manage the watches, and then run the task's command using the
  DebouncingTimer whenever a change is detected in a watched directory or
  file.

  """
  logger.debug("Starting asyncio.Task for {}".format(aTaskName))
  aWatcher = FSWatcher()
  taskLog  = await aiofiles.open(aTask['logFilePath'], 'w')
  aTimer   = DebouncingTimer(1, aTaskName, aTask, taskLog)

  # add watches
  asyncio.create_task(aWatcher.managePathsToWatchQueue())
  for aWatch in aTask['watch'] :
    await aWatcher.watchAPath(aWatch)

  # Ensure the task is run at least once
  await aTimer.reStart()

  # watch and run cmd
  if 'runOnce' not in aTask :
    async for event in aWatcher.watchForFileSystemEvents() :
      await aTimer.reStart()

async def stopTasks() :
  logger.info("Stopping all tasks")
  for aTimer in debouncingTimers :
    await aTimer.stopTaskProc()
    aTimer.cancelTask()
  logger.debug("All tasks Stoped")

shutdownTasks = asyncio.Event()
async def waitForShutdown() :
  logger.debug("waiting for shutdown")
  await shutdownTasks.wait()
  logger.debug("got shutdown")
  await stopTasks()
  logger.debug("shutdown")

async def runTasks(config) :
  """

  Walk through the list of watch-do tasks and create an `asyncio.Task` for
  each task, using an invocation of the `watchDo` method to wrap each task.
  Since these tasks are not Python-CPU bound, they will essentially "run"
  in parallel.

  """

  for aTaskName, aTask in config['tasks'].items() :
    asyncio.create_task(watchDo(aTaskName, aTask))
  await waitForShutdown()
