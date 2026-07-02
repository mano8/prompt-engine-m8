# Docker Compose Security Notes

The compose stack follows the media-service-m8 pattern:

- Traefik uses the file provider only and does not mount the Docker socket.
- Database and Redis run on an internal `data_net` network.
- Application containers drop Linux capabilities, run with `no-new-privileges`, use read-only filesystems, and get writable `tmpfs` mounts only for `/tmp` and `/run`.
- Public HTTPS routes exclude metrics and private auth paths. Internal routes are loopback or stack-subnet restricted by Traefik allowlists.
- Runtime `.env` files are copied from examples by `init.sh` and chmodded to `600`.

Replace every `changethis` placeholder before starting a real stack.