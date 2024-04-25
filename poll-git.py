#!/usr/bin/env python3
import time
import random
from subprocess import check_output

max_interval = 60 * 30
min_interval = 60 * 5

def lerp(a, b, s):
  return (1.0 - s) * a + s * b

def git(*args):
  return check_output(['git', *args])

def clear():
  print(' '*80, end='\r')

def check_for_updates():
  clear()
  print('checking for updates...', end='\r')
  git('remote', 'update')
  status = git('status', '-uno')
  if 'Your branch is up to date with' in status.decode('utf8'):
    clear()
    print('branch is up to date as of', int(time.time() / 60), 'min since epoch', end='\r')
    return
  clear()
  print('updating branch...', end='\r')
  git('pull')

def r(x):
  return int(x * 10) / 10

while True:
  check_for_updates()
  interval = lerp(min_interval, max_interval, random.random())
  clear()
  print('[', r(time.time() / 60), ' min]: sleeping for', r(interval / 60), 'min', end='\r')
  time.sleep(interval)

