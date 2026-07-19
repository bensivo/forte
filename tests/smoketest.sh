#!/bin/bash
#
# A quick smoketest script going through basic operations in a temp dir
#

# Create a temp directory, and initialize a forte vault in it
root_dir=`mktemp -d`
pushd $root_dir
forte init

# Create 2 schemas
forte schema add person --field title --field company --field email
forte schema add meeting --field date --field attendees
forte schema list
## verify: both schemas show up

# Remove one and relist
forte schema remove meeting -y
forte schema list
## verify: only person shows up, not meeting

# Create 3 person entities, and 2 meeting entities
forte entity add person --name Alice --field title=CEO --field company=Example,inc. --field email=alice@example.com
forte entity add person --name Bob --field title=CIO --field company=Example,inc. --field email=bob@example.com
forte entity add person --name Charlie --field title=CFO --field company=Example,inc. --field email=charlie@example.com
forte entity list
## verify: you see all 3 people

forte entity show 1
## verify: you see Alice's details

# Remove Charlie
forte entity remove 3
forte entity list
## verify: Charlie is not present

# Edit Alice's title
forte entity edit 1 --set title=CDO
forte entity show 1
## verify: Alice's title is CDO not CEO

# Rename Bob to Bill
forte entity edit 2 --name Bill
forte entity show 2
## verify: You see 'Bill', not 'Bob'

# Testing listing entities with schema filters
forte entity add meeting --name 1970-01-01-standup --field date=1970-01-01 --field attendees='alice,bob,bill'
forte entity add meeting --name 1970-01-02-standup --field date=1970-01-02 --field attendees='alice,bob,bill'
forte entity list --schema meeting
## verify: you see the right entity when listed


# Go back to the original dir
popd