# First-install rollback

Stop and disable only `orientir-demo.service`. Remove only the newly created
`/etc/nginx/sites-enabled/orientir-demo` link, run `nginx -t`, and gracefully
reload Nginx. Keep `/var/lib/orientir-demo`, `/etc/orientir-demo.env` and releases
for recovery. Do not remove or modify any existing site, certificate or service.

Before later upgrades, use `backup_mentor` and verify the backup. Stop only this
application for migration/cutover. Revert to the prior reviewed release; restore
a matching validated backup if schema changes require it. Never overwrite the
only database. Ordinary restarts must preserve data and the secret key.
