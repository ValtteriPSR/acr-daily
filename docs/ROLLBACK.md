# Release rollback

Keep the previous release tag and source archive, a backup branch at its exact commit, a database snapshot taken before updating, and the previous deployment ID. Never overwrite old release assets.

For a code rollback, deploy the saved 0.2.3 commit or switch the deployment branch to that commit with a new rollback commit. Point the download configuration at a repository whose latest asset is compatible, or temporarily publish the previous installer as the current release without deleting the newer release. Revert the branch, site deployment and latest-release designation together. Preserve new history unless explicitly asked to restore the database snapshot.

0.2.4 adds tables and optional config fields. A previous server ignores new tables, but it cannot enforce the new break protocol. Suspend or remove new-protocol events before accepting old launchers. A code rollback does not undo permanently deleted events. Restoring the pre-update database snapshot restores old data and discards later writes; take a fresh snapshot first and reconcile new results where needed.
