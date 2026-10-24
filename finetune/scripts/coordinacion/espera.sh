#!/bin/bash
until [ -s vigia21.out ]; do sleep 30; done
cat vigia21.out; date +%H:%M
