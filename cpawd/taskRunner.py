import asyncio
import time

from .fsWatcher import FSWatcher

class DebouncingTimer:
  def __init__(self, timeout, taskName, taskCmd, taskLog) :
    self.timeout    = timeout
    self.taskName   = taskName
    self.taskCmd    = taskCmd
    self.taskLog    = taskLog
    self.taskFuture = None

  async def taskRunner(self) :
    await asyncio.sleep(self.timeout)
    proc = await asyncio.create_subprocess_shell(
      self.taskCmd,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.STDOUT
    )

    stdout, stderr = await proc.communicate()

    print(f'Ran: {self.taskName}')
    if stdout:
        self.taskLog.write("\n============================================================================\n")
        self.taskLog.write("stdout @ {}\n".format(time.strftime("%Y/%m/%d %H:%M:%S")))
        self.taskLog.write("{}\n".format(self.taskCmd))
        self.taskLog.write("----------------------------------------------------------------------------\n")
        self.taskLog.write(stdout.decode())
        self.taskLog.write("----------------------------------------------------------------------------\n")
        self.taskLog.flush()
    if stderr:
        self.taskLog.write("\n============================================================================\n")
        self.taskLog.write("stderr @ {}\n".format(time.strftime("%Y/%m/%d %H:%M:%S")))
        self.taskLog.write("{}\n".format(self.taskCmd))
        self.taskLog.write("----------------------------------------------------------------------------\n")
        self.taskLog.write(stderr.decode())
        self.taskLog.write("----------------------------------------------------------------------------\n")
        self.taskLog.flush()

  def reStart(self) :
    if self.taskFuture :
      self.taskFuture.cancel()
    self.taskFuture = asyncio.ensure_future(self.taskRunner())

async def watchDo(aTaskName, aTask) :

  aWatcher = FSWatcher()
  aTimer   = DebouncingTimer(1, aTaskName, aTask['cmd'], aTask['logFile'])

  # add watches
  asyncio.create_task(aWatcher.managePathsToWatchQueue())
  for aWatch in aTask['watch'] :
    await aWatcher.watchAPath(aWatch)

  # watch and run cmd
  async for event in aWatcher.watch_recursive() :
    aTimer.reStart()

async def runTasks(config) :
  cpawdFuture = asyncio.get_event_loop().create_future()
  for aTaskName, aTask in config['tasks'].items() :
    await asyncio.create_task(watchDo(aTaskName, aTask))
  await cpawdFuture

