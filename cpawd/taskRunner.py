"""

This cpawd.taskRunner module implements the running of all watch-do tasks.

It uses the `DebouncingTimer` to actually run the tasks after a short
timeout period. We use this short timeout to ensure the task is only run
once for any collection of changes detected at nearly the same time.

The top level `runTasks` method initiates the `asyncio.Tasks` which
represent each watch-do task.

"""


import asyncio
import time

from .fsWatcher import FSWatcher

class DebouncingTimer:
  """

  The DebouncingTimer class implements a simple timer to ensure multiple
  file system events result in only one invocation of the task command.

  """

  def __init__(self, timeout, taskName, taskDetails) :
    """
    Create the timer with a specific timeout and task definition.

    The taskDetails provides the command to run, the log file used to
    record command output, as well as the project directory in which to
    run the command.

    """

    self.timeout    = timeout
    self.taskName   = taskName
    self.taskCmd    = taskDetails['cmd']
    self.taskLog    = taskDetails['logFile']
    self.taskDir    = taskDetails['projectDir']
    self.taskFuture = None

  async def taskRunner(self) :
    """

    Run the task's command, after sleeping for the timeout period, using
    `asyncio.create_subprocess_shell` command.

    """

    await asyncio.sleep(self.timeout)
    proc = await asyncio.create_subprocess_shell(
      self.taskCmd,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.STDOUT,
      cwd=self.taskDir
    )

    stdout, stderr = await proc.communicate()

    print(f'Ran: {self.taskName}')
    if stdout:
        self.taskLog.write("\n============================================================================\n")
        self.taskLog.write("{} stdout @ {}\n".format(self.taskName, time.strftime("%Y/%m/%d %H:%M:%S")))
        self.taskLog.write("{}\n".format(self.taskCmd))
        self.taskLog.write("----------------------------------------------------------------------------\n")
        self.taskLog.write(stdout.decode())
        self.taskLog.write("----------------------------------------------------------------------------\n")
        self.taskLog.flush()
    if stderr:
        self.taskLog.write("\n============================================================================\n")
        self.taskLog.write("{} stderr @ {}\n".format(self.taskName, time.strftime("%Y/%m/%d %H:%M:%S")))
        self.taskLog.write("{}\n".format(self.taskCmd))
        self.taskLog.write("----------------------------------------------------------------------------\n")
        self.taskLog.write(stderr.decode())
        self.taskLog.write("----------------------------------------------------------------------------\n")
        self.taskLog.flush()

  def reStart(self) :
    """

    (Re)Start the timer. If the timer is already started, it is restarted
    with a new timeout period.

    """

    if self.taskFuture :
      self.taskFuture.cancel()
    self.taskFuture = asyncio.ensure_future(self.taskRunner())

async def watchDo(aTaskName, aTask) :
  """

  Setup and manage the watches, and then run the task's command using the
  DebouncingTimer whenever a change is detected in a watched directory or
  file.

  """

  aWatcher = FSWatcher()
  aTimer   = DebouncingTimer(1, aTaskName, aTask)

  # add watches
  asyncio.create_task(aWatcher.managePathsToWatchQueue())
  for aWatch in aTask['watch'] :
    await aWatcher.watchAPath(aWatch)

  # watch and run cmd
  async for event in aWatcher.watchForFileSystemEvents() :
    aTimer.reStart()

async def runTasks(config) :
  """

  Walk through the list of watch-do tasks and create an `asyncio.Task` for
  each task, using an invocation of the `watchDo` method to wrap each task.
  Since these tasks are not Python-CPU bound, they will essentially "run"
  in parallel.

  """

  cpawdFuture = asyncio.get_event_loop().create_future()
  for aTaskName, aTask in config['tasks'].items() :
    await asyncio.create_task(watchDo(aTaskName, aTask))
  await cpawdFuture

