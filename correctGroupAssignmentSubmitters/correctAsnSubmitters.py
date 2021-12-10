#!/usr/bin/python3
# Filename: correctAsnSubmitters.py
# Generates SQL to re-synchronize group assignment submissions' submitters with their group membership
# This script assumes the data is pulled from Oracle (E.g. boolean values are '0'/'1', null is "")

import csv
import os

####################### Configuration #######################

GROUP_MEMBERS_FILE_NAME = "inputFiles/groupMembers.csv"
ASN_SUBMISSION_FILE_NAME = "inputFiles/asn_submission.csv"
ASN_SUBMISSION_SUBMITTER_FILE_NAME = "inputFiles/asn_submission_submitter.csv"

OUTPUT_DIRECTORY = './outputFiles'
OUTPUT_FILE = 'output.sql'

DELIMITER = ','

# asn_submission_submitter column order:
ID_INDEX = 0
FEEDBACK_INDEX = 1
GRADE_INDEX = 2
SUBMITTEE_INDEX = 3
SUBMITTER_INDEX = 4
SUBMISSION_ID_INDEX = 5

DEBUG = 0


######################## Functions ########################

def output(text):
	outputFile.write(text + "\n")

def cleanupAndExit():
	groupMembersFile.close()
	submissionsFile.close()
	submittersFile.close()
	outputFile.close()
	exit()

######################## Main Logic ########################

# Read the files:
groupMembersFile = open(GROUP_MEMBERS_FILE_NAME)
submissionsFile = open(ASN_SUBMISSION_FILE_NAME)
submittersFile = open(ASN_SUBMISSION_SUBMITTER_FILE_NAME)

# Actual group members from sakai_realm_rl_gr. Columns: user_id, group_id
usersToRealmGroups = dict(csv.reader(groupMembersFile, delimiter=DELIMITER))

# Assignment submissions' associated groups from asn_submission. Columns: submission_id, group_id 
submissionsToGroups = dict(csv.reader(submissionsFile))
# Back-up (does not benefit the current implementation, but will be needed if we have a case where a submittee submitted to the wrong group):
originalSubmissionsToGroups = submissionsToGroups.copy()

# Rows of asn_submission_submitter. Columns: id, feedback, grade, submittee, submitter, submission_id
submitters = list(csv.reader(submittersFile))

# Prepare the output directory
if not os.path.exists(OUTPUT_DIRECTORY):
	os.makedirs(OUTPUT_DIRECTORY)

outputFile = open(OUTPUT_DIRECTORY + "/" + OUTPUT_FILE, "w")

"""
=================================================================================
VALIDATION PASS:
1) Detect unhandled cases:
	presence of feedback,
	presence of grades,
	submittees who submitted on the wrong group's submission
2) Map usersToSubmissionGroups: submitters -> their associated submissions' groups
=================================================================================
"""

# Maps users to the lists of groups they have submissions associated with (E.g. submitters -> submissions -> groups are usually, but not always 1 : 1 : 1)
usersToSubmissionGroups = {}
for submitter in submitters:
	if submitter[FEEDBACK_INDEX] != "":
		print("Submitter-specific feedback has been detected; revisit how to deal with this")
		cleanupAndExit()
	if submitter[GRADE_INDEX] != "":
		print("A submitter-specific grade has been detected; revisit how to deal with this")
		cleanupAndExit()

	userId = submitter[SUBMITTER_INDEX]
	submissionId = submitter[SUBMISSION_ID_INDEX]
	submissionGroup = originalSubmissionsToGroups[submissionId]
	
	# Some users have multiple asn_submission_submitter rows (E.g. they appear on multiple submissions)
	usersGroups = usersToSubmissionGroups.get(userId, [])
	usersGroups.append(submissionGroup)
	usersToSubmissionGroups[userId] = usersGroups

	if submitter[SUBMITTEE_INDEX] == "1":
		assignmentSubmissionGroup = submissionsToGroups[submissionId]
		submitteeGroup = usersToRealmGroups[userId]

		if assignmentSubmissionGroup != submitteeGroup:
			print("Submittee: " + userId + " submitted for " + assignmentSubmissionGroup + ", their actual group: " + submitteeGroup + ". This case is untested; exiting")
			# Memberships should be corrected such that this submission will be associated with the submittee's group
			submissionsToGroups[submissionId] = submitteeGoup
			# "update asn_submission" statements will be required: the submittee's associated asn_submission.group_id will need to point at the submittee's actual group.
			# If another asn_submission points at the submittee's actual group, it may need to have its group_id swapped with this submission's group.
			cleanupAndExit()


if len(submissionsToGroups) != len(set(submissionsToGroups.values())):
	print("SubmissionsToGroups - multiple submissions are associated with the same groups; revisit how to deal with this")
	cleanupAndExit()

groupsToSubmissions = {group: submission for submission, group in submissionsToGroups.items()}

"""
==============================================================================================================================
DETECTION PASS:
Detect additions: any sakai_realm_rl_gr members whose group is not in their asn_submission_submitter's submission's group
Detect removals: any asn_submission_submitters whose submission's group differs from the user's actual sakai_realm_rl_gr group
Users who have both an addition and a removal will be 'updated'.
==============================================================================================================================
"""

# userId: groupId mappings that exist in the group realms, but not in asn_submission_submitter:
toAdd = {}
for userId in usersToRealmGroups:
	actualGroupId = usersToRealmGroups[userId]
	if actualGroupId not in usersToSubmissionGroups.get(userId, []):
		# The user doesn't have any submissions associated with their actual group
		toAdd[userId] = actualGroupId

# asn_submission_submitter rows whose submissions' group do not reflect the submitter's group:
toRemove = []
for submitter in submitters:
	userId = submitter[SUBMITTER_INDEX]
	groupsFromSubmissions = usersToSubmissionGroups.get(userId, [])
	if usersToRealmGroups.get(userId, "") not in groupsFromSubmissions:
		# None of the user's submissions's groups match the user's actual group; remove all their asn_submission_submitter entries
		toRemove.append(submitter)
		if submitter[SUBMITTEE_INDEX] == "1":
			print("Warning: A submittee entry is in toRemove.")
	elif len(groupsFromSubmissions) > 1:
		# The user has multiple asn_submission_submitter entries (I.e. associated with different submissions.)
		# Get this submitter's submission's group; if it doesn't match the user's actual group, delete this asn_submission_submitter row.
		submissionId = submitter[SUBMISSION_ID_INDEX]
		if submissionsToGroups[submissionId] != usersToRealmGroups[userId]:
			toRemove.append(submitter)
			if submitter[SUBMITTEE_INDEX] == "1":
				print("Warning: A submittee entry is in toRemove; this is not the user's only submission.")

if (DEBUG):
	print("To remove:")
	print(toRemove)
	print("To add:")
	print(toAdd)


"""
===================================================================================================================================================
OUTPUT CORRECTION SQL:
For all submitters whose submission's groups differ from their actual sakai_realm_rl_gr membership
	update their submitter > submission_id such that it points to the submission associated with their actual sakai_realm_rl_gr group
If the user isn't actually in a sakai_realm_rl_gr group associated with the assignment, then they're not authorized; so delete their submitter row.

For all users who are in the assignment's assigned groups, but do not have an a asn_submission_submitter row, insert one
===================================================================================================================================================
"""

for submitter in toRemove:
	userId = submitter[SUBMITTER_INDEX]
	groupToSwitchTo = toAdd.get(userId, "")
	if groupToSwitchTo != "":
		# Create an update statement, then remove the user from toAdd
		submissionId = groupsToSubmissions[groupToSwitchTo]
		output("-- Before update: {0}".format(str(submitter)))
		statement = "update sakaiadmin.asn_submission_submitter set submission_id = '{0}' where id = {1};".format(submissionId, submitter[ID_INDEX])
		output(statement)
		toAdd.pop(userId)
	else:
		# Create a delete statement
		output("-- Back-up: {0}".format(str(submitter)))
		statement = "delete from sakaiadmin.asn_submission_submitter where id = {0};".format(submitter[ID_INDEX])
		output(statement)
	output("")

output("-- Users in the submissions' groups, but who do not have asn_submission_submitter entries")
for userId in toAdd:
	# Create the insert statement
	# The sequence name according to the upgrade script: ASN_SUBMISSION_SUBMITTERS_S
	submissionId = groupsToSubmissions[toAdd[userId]]
	statement = """insert into sakaiadmin.asn_submission_submitter (id, feedback, grade, submittee, submitter, submission_id) 
	values (ASN_SUBMISSION_SUBMITTERS_S.nextval, "", "", 0, '{0}', '{1}');""".format(userId, submissionId)
	output(statement)

output("commit;")

groupMembersFile.close()
submissionsFile.close()
submittersFile.close()
outputFile.close()

print("Success!")
