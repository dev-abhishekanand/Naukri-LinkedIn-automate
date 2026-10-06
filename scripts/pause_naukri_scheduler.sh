#!/bin/zsh

LABEL="com.naukri.linkedin-ai.naukri"

launchctl bootout "gui/$(id -u)/$LABEL"

echo "Naukri scheduler paused."
echo "The installed plist and all application/runtime data remain untouched."
