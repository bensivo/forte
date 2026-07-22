#!/bin/bash
#
# A smoketest for the agent pipeline: ingests every doc in one of the
# tests/fixtures e2e folders via `forte agent ingest -y`, so entities and
# links get extracted automatically instead of by hand.
#

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fixtures_dir="$script_dir/fixtures/e2e_meeting_notes"
# fixtures_dir="$script_dir/fixtures/e2e_client_emails"
# fixtures_dir="$script_dir/fixtures/e2e_recipes"

# Create a temp directory, and initialize a forte vault in it
root_dir=`mktemp -d`
pushd $root_dir
forte init

forte schema add project
forte schema add person
forte schema add task
forte schema add meeting
forte schema add email
forte schema add recipes
forte schema add ingredients

# Ingest every doc in the fixture folder, running the agent pipeline on each
for f in "$fixtures_dir"/*; do
  forte agent ingest "$f" -y
done

forte doc list
## verify: all 5 meeting notes show up as docs

forte entity list
## verify: people and other entities (Sarah Chen, Raj Patel, Project Lighthouse, etc.) were extracted

# Go back to the original dir
popd
