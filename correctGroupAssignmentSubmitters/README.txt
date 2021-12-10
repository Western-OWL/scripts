Assignments copies group memberships for group assignment submissions. For unknown reasons, these assignment submission group memberships sometimes mismatch the site's actual group memberships.
Use the following steps to correct group assignments whose memberships are out of sync:

1) Run and export the following queries. Do not include headers. Save them in ./inputFiles:

Export these results as groupMembers.csv:
select rlgr.user_id, substr(realm.realm_id, 50) as group_id  from sakai_realm realm join sakai_realm_rl_gr rlgr on realm.realm_key = rlgr.realm_key where realm.realm_id in (
	select group_id from sakaiadmin.asn_assignment_groups where assignment_id = '<ASSIGNMENT_ID_HERE>'
);

Export these results as asn_submission.csv:
select submission_id, group_id from sakaiadmin.asn_submission where assignment_id = '<ASSIGNMENT_ID_HERE>';

Export these results as asn_submission_submitter.csv:
select id, feedback, grade, submittee, submitter, submission_id from sakaiadmin.asn_submission_submitter where submission_id in (
	select submission_id from sakaiadmin.asn_submission where assignment_id = '<ASSIGNMENT_ID_HERE>'
);

2) Execute the following:
python3 correctAsnSubmitters.py

3) Watch for any warnings, test against a restore environmenti if possible. When confident to proceed, attach it to a ticket for the DBAs for production.

