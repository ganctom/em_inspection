import paramiko


class ClusterService:
    def __init__(self, host="cluster.internal", user="ganctoma"):
        self.host = host
        self.user = user

    def submit_sbatch(self, script_content, remote_path):
        """Uploads script via SFTP and executes sbatch via SSH."""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            # allow_agent=True uses the key you just added with ssh-add
            ssh.connect(self.host, username=self.user, allow_agent=True)

            # 1. Upload the script
            sftp = ssh.open_sftp()
            with sftp.file(remote_path, 'w') as f:
                f.write(script_content)
            sftp.chmod(remote_path, 0o755)
            sftp.close()

            # 2. Execute sbatch
            stdin, stdout, stderr = ssh.exec_command(f"sbatch {remote_path}")

            job_out = stdout.read().decode().strip()
            job_err = stderr.read().decode().strip()
            ssh.close()

            return job_out if job_out else job_err
        except Exception as e:
            return f"Deployment Error: {str(e)}"