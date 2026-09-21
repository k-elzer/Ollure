import discord
from discord.ext import commands
import paramiko
from dotenv import load_dotenv
import os
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

# Optional local secrets file (kept out of git) that can override values from .env
# SECRET FILE IMPLEMENTATION WAS A SUGGESTION FROM COPILOT
load_dotenv(SCRIPT_DIR / ".env.secret", override=True)

def resolve_env_path(path_value: str) -> Path:
    """Resolve environment variables, user home markers, and relative paths."""
    expanded_path = os.path.expandvars(path_value.strip())
    raw_path = Path(expanded_path).expanduser()
    if raw_path.is_absolute():
        return raw_path
    return (SCRIPT_DIR / raw_path).resolve()


# ==========================================================
# ==========================================================
# ==========================================================
# ==========================================================
# ==========================================================


# ! THIS VALUE DECIDES WHETHER TO CHECK THE AWS EC2 INSTANCE, THE DIGITALOCEAN DROPLET, OR THE UNI-HOSTED VM:

cloud_specifier = "dtu"

cloud_platform = ""
if cloud_specifier == "ec2":
    cloud_platform = "ec2_mih"
elif cloud_specifier == "droplet":
    cloud_platform = "droplet_mih"
elif cloud_specifier == "dtu" or cloud_specifier == "uni":
    cloud_platform = "uni_mih"
else:
    raise ValueError(f"Invalid cloud_specifier: {cloud_specifier}. Must be 'ec2', 'droplet', or 'dtu'|'uni'.")

# ==========================================================
# ==========================================================
# ==========================================================
# ==========================================================
# ==========================================================


TOKEN = os.getenv("DISCORD_BOT_TOKEN") # this will be grabbed from the ".env.secret" file, located alongside the ".env" file!

PUBLIC_IP = None
PUBLIC_DNS = None
TCPDUMP_FILTER_IP = None # value to use for the tcpdump filter # ! (EC2 logs contain the internal IP, while Droplet logs contain the public IP!!!)
KEY_PATH = None
KEY_PWD = None # only overwritten for DigitalOcean access
BASE_LOG_DIRECTORY_NAME = os.getenv("BASE_LOG_DIRECTORY_NAME")
FULL_BASE_LOG_PATH = None


pkcs1 = None # will contain the private key for the UNI honeypot jump how later, if this is the cloud platform being used

# set various cloud platform-specific variables
if cloud_platform == "ec2_mih":
    PUBLIC_IP = os.getenv("EC2_DASHED_PUBLIC_IP").replace("-", ".") # dash-formatted IP used for public DNS so just convert that here for the actual IP
    PUBLIC_DNS = os.getenv("EC2_PUBLIC_DNS")
    CLOUD_USER = os.getenv("CLOUD_USER")
    FULL_BASE_LOG_PATH = f"/home/{CLOUD_USER}{BASE_LOG_DIRECTORY_NAME}"
    TCPDUMP_FILTER_IP = os.getenv("MIH_EC2_INTERNAL_IP", "").strip() # grabbed from ".env.secret"
    KEY_PATH = os.getenv("PEM_KEY_PATH")
    KEY_PATH = str(resolve_env_path(KEY_PATH))

elif cloud_platform == "droplet_mih":
    PUBLIC_IP = os.getenv("DROPLET_EXTERNAL_IP")
    PUBLIC_DNS = PUBLIC_IP
    CLOUD_USER = os.getenv("CLOUD_USER")
    FULL_BASE_LOG_PATH = f"/home/{CLOUD_USER}{BASE_LOG_DIRECTORY_NAME}"
    TCPDUMP_FILTER_IP = os.getenv("DROPLET_EXTERNAL_IP", "").strip() # ? DigitalOcean Droplet traffic contains the public IP instead of the droplets' internal IPs, so using the external is intentional!
    KEY_PATH = os.getenv("SSH_KEY_PATH")
    KEY_PATH = str(resolve_env_path(KEY_PATH))
    KEY_PWD = os.getenv("SSH_KEY_PWD") # grabbed from ".env.secret

elif cloud_platform == "uni_mih":
    PUBLIC_DNS = "chproxy.compute.dtu.dk"
    NESTED_VM_USER = os.getenv("NESTED_VM_USER")
    FULL_BASE_LOG_PATH = f"/home/{NESTED_VM_USER}{BASE_LOG_DIRECTORY_NAME}"
    UNI_VM_HOSTNAME = os.getenv("DTU_VM_HOSTNAME")
    HP_MH_VM_HOSTNAME = os.getenv("HP_MH_VM_HOSTNAME") # grabbed from ".env.secret"
    CLOUD_USER = os.getenv("STUDENT_ID") # grabbed from ".env.secret"
    KEY_FILE = os.getenv("OPENVPN_KEY_FILE") # grabbed from ".env.secret"
    KEY_PATH = os.getenv("OPENVPN_KEY_CONFIG_PATH")
    KEY_PATH = f"{KEY_PATH}\\openvpn-{CLOUD_USER}\\{KEY_FILE}"
    KEY_PATH = str(resolve_env_path(KEY_PATH))
    PROXY_RELATIVE_KEY_PATH = os.getenv("PROXY_RELATIVE_KEY_PATH")
    KEY_PWD = os.getenv("VPN_PWD") # grabbed from ".env.secret"



HOST_LOG_DIR = str(os.getenv("HOST_LOG_DIR"))
HOST_LOG_DIR = str(resolve_env_path(HOST_LOG_DIR))

HP_IMAGE_NAME = os.getenv("HP_IMAGE_NAME")
HP_CONTAINER = os.getenv("HP_CONTAINER_NAME")
TCPDUMP_CONTAINER = os.getenv("TCPDUMP_CONTAINER_NAME")
CONTAINER_LOG_PATH = os.getenv("CONTAINER_LOG_PATH")
CONTAINER_LOG_FILE_NAME = os.getenv("CONTAINER_LOG_FILE_NAME")

intents = discord.Intents.all() # using all intents for now # TODO: figure out if I should use '.default()' instead, or something different!
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def run_ssh(command):
    # this jump host is only needed for the UNI-hosted honeypot as it sits behind a proxy
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # "KEY_PWD" is None by default, and only set to a password for DigitalOcean access (password gotten from ".env.secret")
    # (note the use of different key types used for the two ".from_private_key_file()" methods)
    # ? the uni-hosted vm doesn't use an SSH key, so no need to check for this case
    if cloud_platform == "ec2_mih":
        key = paramiko.RSAKey.from_private_key_file(filename=KEY_PATH)
    elif cloud_platform == "droplet_mih":
        key = paramiko.Ed25519Key.from_private_key_file(filename=KEY_PATH, password=KEY_PWD)

    # init the output variables
    stdin, stdout, stderr = None, None, None

    # for the UNI-hosted honeypots, the first SSH connection is to a proxy, so SSH once more to reach the actual honeypot VM
    if cloud_platform == "uni_mih":
        client.connect(
            hostname=PUBLIC_DNS,
            username=CLOUD_USER,
            password=KEY_PWD, # "passphrase" is apparently not the right function argument to use. Ask me how I know ;-;
            timeout=10
        )
        # run the nested SSH command with the given command to be executed
        stdin, stdout, stderr = client.exec_command(f"ssh {UNI_VM_HOSTNAME} '{command}'")

    else:
        client.connect(
            hostname=PUBLIC_DNS,
            username=CLOUD_USER,
            pkey=key,
            timeout=10
        )
        stdin, stdout, stderr = client.exec_command(command)

    code = stdout.channel.recv_exit_status()
    output = stdout.read().decode("utf-8", errors="replace").strip()
    error = stderr.read().decode("utf-8", errors="replace").strip()

    client.close()

    return code, output, error

# function to copy a file from the cloud platform (either the EC2 instance or the DigitalOcean droplet) to the host machine running this bot
# ? NOTE THAT THE REMOTE PATH SPECIFIED MUST BE THE FULL FILEPATH - Local file is created if it doesn't exist as long as the parent directories exist already
# SUGGESTED BY COPILOT, WITH MINOR KEY-DECISION TWEAKS ADDED
def transfer_file(remote_file_path: str, local_file_path: str):
    """Fetch a file from droplet via SFTP instead of scp."""

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # "KEY_PWD" is None by default, and only set to a password for DigitalOcean access (password gotten from ".env.secret")
    # (note the use of different key types used for the two ".from_private_key_file()" methods)
    # ? the uni-hosted vm doesn't use an SSH key, so no need to check for this case
    if cloud_platform == "ec2_mih":
        key = paramiko.RSAKey.from_private_key_file(filename=KEY_PATH)
    elif cloud_platform == "droplet_mih":
        key = paramiko.Ed25519Key.from_private_key_file(filename=KEY_PATH, password=KEY_PWD)

    # init the output variable
    stdout = None

    # for the UNI-hosted honeypots, the first SSH connection is to a proxy, so SSH once more to reach the actual honeypot VM
    if cloud_platform == "uni_mih":
        client.connect(
            hostname=PUBLIC_DNS,
            username=CLOUD_USER,
            password=KEY_PWD, # "passphrase" is apparently not the right function argument to use. Ask me how I know ;-;
            timeout=10
        )
        # run the nested SSH command from the jumphost and fetch the file contents over this local<->proxy<->VM SSH connection
        stdin, stdout, stderr = client.exec_command(
            f"ssh {UNI_VM_HOSTNAME} 'cat {remote_file_path}'"
        )

    else:
        client.connect(
            hostname=PUBLIC_DNS,
            username=CLOUD_USER,
            pkey=key,
            timeout=10
        )
        # if not fetching from the UNI-hosted honeypot, simply cat the file contents over the established SSH connection
        stdin, stdout, stderr = client.exec_command(
            f"cat {remote_file_path}"
        )

    with open(local_file_path, "wb") as f:
        f.write(stdout.read())

    client.close()


# function to copy all files from a given directory on the cloud platform (either the EC2 instance or the DigitalOcean droplet) to the host machine running this bot
# ? NOTE THAT THE REMOTE DIRECTORY SPECIFIED MUST BE THE FULL DIRECTORY - Local directory *IS NOT* created if it doesn't already exist
# SUGGESTED BY COPILOT, WITH MINOR KEY-DECISION TWEAKS ADDED
def transfer_files_from_dir(remote_dir: str, local_dir: str, suffix: str = "honeypot") -> tuple[int, int]:
    # this jump host is only needed for the UNI-hosted honeypot as it sits behind a proxy
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # ? the uni-hosted vm doesn't use an SSH key, so no need to check for this case
    if cloud_platform == "ec2_mih":
        key = paramiko.RSAKey.from_private_key_file(filename=KEY_PATH)
    elif cloud_platform == "droplet_mih":
        key = paramiko.Ed25519Key.from_private_key_file(filename=KEY_PATH, password=KEY_PWD)

    # init the output variable
    stdout, stderr = None, None

    # for the UNI-hosted honeypots, the first SSH connection is to a proxy, so SSH once more to reach the actual honeypot VM
    if cloud_platform == "uni_mih":
        client.connect(
            hostname=PUBLIC_DNS,
            username=CLOUD_USER,
            password=KEY_PWD, # "passphrase" is apparently not the right function argument to use. Ask me how I know ;-;
            timeout=10
        )

        # run the nested SSH command from the jumphost and tar-zip the given directory,
        # outputting the gzip in stdout due to the '-' output location,
        # and sending contents over this local<->proxy<->VM SSH connection
        stdin, stdout, stderr = client.exec_command(
            f"ssh {UNI_VM_HOSTNAME} 'tar -czf - -C {remote_dir} .'"
        )

    else:
        client.connect(
            hostname=PUBLIC_DNS,
            username=CLOUD_USER,
            pkey=key,
            timeout=10
        )
        # if not fetching from the UNI-hosted honeypot, simply cat the file contents over the established SSH connection
        stdin, stdout, stderr = client.exec_command(
            f"tar -czf - -C {remote_dir} ."
        )

    # folder name "remote_pcaps.tar.gz" is simply a temporary archive to store the pcaps,
    # and will be deleted after extracting the archive
    with open(f"{local_dir}\\remote_pcaps.tar.gz", "wb") as f:
        f.write(stdout.read())

    if not Path(f"{local_dir}\\remote_pcaps.tar.gz").exists():
        return Exception(f"Error locating gzip archive: {stderr.read().decode()}")

    # extract the tar.gz archive to the given local directory
    tar_exit_code = os.system(f"tar -xf {local_dir}\\remote_pcaps.tar.gz -C {local_dir}")

    # removed the extracted gzip archive
    # ? (this simply assumes that the file extraction was successful)
    archive_removal_exit_code = os.system(f"del {local_dir}\\remote_pcaps.tar.gz")

    client.close()

    # return last file so the copy can be verified after the method call
    return tar_exit_code, archive_removal_exit_code




# ======================================================================
# ======= BOT COMMANDS MAKE USE OF DISCORD TEXT COLOR FORMATTING =======
# ======================================================================
# ======================== GUIDE USED FOR THIS: ========================
# ========= https://www.writebots.com/discord-text-formatting/ =========
# ======================================================================



# ====================== PREPARED COMMAND STRINGS ======================

recreate_hp_cmd = (
    f"docker run -d --restart unless-stopped "
    f"--name {HP_CONTAINER} "
    f"--network host "
    f"--mount type=bind,src=/{FULL_BASE_LOG_PATH}/honeypot-logs,dst={CONTAINER_LOG_PATH}/ " # ? including leading slash to avoid relative path issues
    f"-e LOG_DIR={CONTAINER_LOG_PATH}/ "
    f"{HP_IMAGE_NAME}"
)


# "--network host" is required for tcpdump to see all traffic hitting the network,
# rather than only what targets the honeypot on port 11434
recreate_tcpdump_cmd = (
    f"docker run -d --restart unless-stopped "
    f"--name {TCPDUMP_CONTAINER} "
    f"--network host "
    f"-v /{FULL_BASE_LOG_PATH}/tcpdump-logs/:/tcpdump-logs " # ? including leading slash to avoid relative path issues
    f"--entrypoint /bin/sh " # needed for 'umask 027' to be applied to the tcpdump command later    
    f"kaazing/tcpdump "
    f"-c \"umask 027; " # ? <-- start of a shell command!
    f"exec tcpdump "
    f"-i any port 11434 " # only keep traffic related to port 11434
    f"-G 86400 " # rotate logs every 24 hours (86400 seconds)
    f"-w /tcpdump-logs/%Y-%m-%d_%H-%M-%S-{cloud_platform}_honeypot.pcap\"" # ? <-- end of the shell command!
)


# ======================== DISCORD BOT COMMANDS ========================


# simple event used to show that the bot is ready,
# with text being printed using ANSI color codes in the same format as used in Blender build scripts
# (source for these: https://stackoverflow.com/questions/287871/how-do-i-print-colored-text-to-the-terminal)
# "\033" is to denote an octal escape sequence,
# "\033[91m" is the ANSI escape code for red text,
# "\033[92m" is the ANSI escape code for green text,
# "\033[93m" is the ANSI escape code for yellow text,
# "\033[96m" is the ANSI escape code for cyan text,
@bot.event
async def on_ready():
    print("BOT IS READY!")
    print("Checking Cloud Platform:")
    if cloud_platform == "ec2_mih":
        print(
            f"{'\033[93m'}AWS EC2:{'\033[0m'}"
        )
    elif cloud_platform == "droplet_mih":
        print(
            f"{'\033[96m'}DIGITALOCEAN DROPLET:{'\033[0m'}"
        )
    elif cloud_platform == "uni_mih":
        print(
            f"{'\033[91m'}UNI-HOSTED VM:{'\033[0m'}"
        )
    print(f"{'\033[92m'}>>> MIH <<<{'\033[0m'}")


# debug command for inspecting potential permission issues
# decided to keep this around in case of future tomfoolery regarding permissions
@bot.command()
async def debug(ctx):
    echo1_code, echo1_output, echo1_error = run_ssh("echo \"UID: $(id -u) GID: $(id -g)\"")
    await ctx.send(
        "echo UID and GID check:\n"
        f"echo_code: {echo1_code}\n"
        f"echo_output: {echo1_output}\n"
        f"echo_error: {echo1_error}"
    )

    echo2_code, echo2_output, echo2_error = run_ssh("echo \"Groups: $(groups)\"")
    await ctx.send(
        "echo Groups check:\n"
        f"echo_code: {echo2_code}\n"
        f"echo_output: {echo2_output}\n"
        f"echo_error: {echo2_error}"
    )

    docker_code, docker_output, docker_error = run_ssh("docker ps -a")
    await ctx.send(
        "docker ps -a check:\n"
        f"docker_code: {docker_code}\n"
        f"docker_output: {docker_output}\n"
        f"docker_error: {docker_error}"
    )

    echo3_code, echo3_output, echo3_error = run_ssh(f"echo \"ENV FULL_BASE_LOG_PATH: {FULL_BASE_LOG_PATH}\"")
    await ctx.send(
        "echo ENV check:\n"
        f"echo_code: {echo3_code}\n"
        f"echo_output: {echo3_output}\n"
        f"echo_error: {echo3_error}"
    )
    
    



# debugging command to check if bot is working and listening for commands,
# and also used to test individual functions
@bot.command()
async def test(ctx):
    remote_dir = f"{FULL_BASE_LOG_PATH}/tcpdump-logs"
    local_dir = f"{HOST_LOG_DIR}\\tcp_logs"

    print(f"remote directory path: {remote_dir}")
    print(f"local directory path: {local_dir}")

    tar_exit_code, archive_removal_exit_code = transfer_files_from_dir(remote_dir, local_dir)

    if tar_exit_code != 0:
        await ctx.send(
            f"```diff\n"
            f"- ERROR EXTRACTING ARCHIVE AFTER nested ssh file stream attempt!\n"
            f"```"
        )
    elif archive_removal_exit_code != 0:
        await ctx.send(
            f"```diff\n"
            f"- ERROR DELETING ARCHIVE AFTER nested ssh file stream attempt!\n"
            f"```"
        )
    else:
        await ctx.send(
            f"```ini\n"
            f"[THE NESTED SSH FILE STREAM WORKED!]\n"
            f"```"
        )

    await ctx.send("This is a test command. Bot is working!")


# command to check container status(es)
@bot.command()
async def psall(ctx):
    try:
        code, output, error = run_ssh("docker ps -a")

        if code != 0:
            await ctx.send(
                f"```diff\n"
                f"- DOCKER CONTAINER INSPECTION ERROR!\n"
                f"```"
                f"```ERROR:\n\n{error}```"
            )
        else:
            await ctx.send(
                f"```diff\n"
                f"+ Docker container inspection successful\n"
                f"```"
                f"```Output:\n\n{output}```"
            )

    except Exception as e:
        await ctx.send(
            f"```diff\n"
            f"- EXCEPTION ERROR!\n"
            f"```"
            f"```ERROR:\n\n{str(e)}```"
        )


# check if honeypot container is running, and if not, recreate it
# (since containers only get started with "docker run -rm", if container isn't running, it doesn't exist)
@bot.command()
async def honey(ctx):
    try:
        check_hp_cmd = f"docker container inspect -f '{{{{.State.Status}}}}' {HP_CONTAINER}"
        code, output, error = run_ssh(check_hp_cmd)

        # print("after checking honeypot container status")

        if "no such container" in error.lower() or "running" not in output.lower():
            await ctx.send(
                f"```ini\n"
                f"[Honeypot container wasn't running]\n"
                f"```"
                f"*Recreating Honeypot container...*"
            )

            # forcibly remove the honeypot container before trying to recreate it
            remove_HP_cmd = f"docker rm -f {HP_CONTAINER} 2>/dev/null || true"
            run_ssh(remove_HP_cmd)

            # recreate the honeypot container, now that it was forcibly removed if it existed
            run_ssh(recreate_hp_cmd)

        # print("after possibly recreating honeypot container")

        # re-check container status after potential recreation
        check_hp_cmd = f"docker container inspect -f '{{{{.State.Status}}}}' {HP_CONTAINER}"
        hp_code, hp_output, hp_error = run_ssh(check_hp_cmd)

        # print("after re-checking honeypot container status")

        if hp_code != 0:
            await ctx.send(
                f"```diff\n"
                f"- HONEYPOT INSPECTION ERROR!\n"
                f"```"
                f"```ERROR:\n\n{hp_error}```"
            )
        else:
            await ctx.send(
                f"```diff\n"
                f"+ Honeypot container inspection successful\n"
                f"```"
                f"```Container Status:\n\n{hp_output}```"
            )

    except Exception as e:
        await ctx.send(
            f"```diff\n"
            f"- EXCEPTION ERROR!\n"
            f"```"
            f"```ERROR:\n\n{str(e)}```"
        )


# check if tcpdump container is running, and if not, recreate it
# (since containers only get started with "docker run -rm", if container isn't running, it doesn't exist)
@bot.command()
async def tcp(ctx):
    try:
        check_tcpdump_cmd = f"docker container inspect -f '{{{{.State.Status}}}}' {TCPDUMP_CONTAINER}"
        code, output, error = run_ssh(check_tcpdump_cmd)

        # print("after checking tcpdump container status")

        if "no such container" in error.lower() or "running" not in output.lower():
            await ctx.send(
                f"```ini\n"
                f"[TCPDUMP container wasn't running]\n"
                f"```"
                f"*Recreating TCPDUMP container...*"
            )

            # forcibly remove the tcpdump container before trying to recreate it
            remove_TCPDUMP_cmd = f"docker rm -f {TCPDUMP_CONTAINER} 2>/dev/null || true"
            _, stdout, stderr = run_ssh(remove_TCPDUMP_cmd)

            # recreate the tcpdump container, now that it was forcibly removed if it existed.
            # The rerun command here doesn't use '-p' because it instead uses the host network directly
            # (necessary for logging the correct source IPs, and for tcpdump to see traffic at all)
            _, stdout, stderr = run_ssh(recreate_tcpdump_cmd)
            # print(f"stdout:\n{stdout}\nstderr:\n{stderr}")

        # print("after possibly recreating tcpdump container")

        # re-check container status after potential recreation
        check_tcpdump_cmd = f"docker container inspect -f '{{{{.State.Status}}}}' {TCPDUMP_CONTAINER}"
        tcpdump_code, tcpdump_output, tcpdump_error = run_ssh(check_tcpdump_cmd)

        # print("after re-checking tcpdump container status")

        if tcpdump_code != 0:
            await ctx.send(
                f"```diff\n"
                f"- TCPDUMP INSPECTION ERROR!\n"
                f"```"
                f"```ERROR:\n\n{tcpdump_error}```"
            )
        else:
            await ctx.send(
                f"```diff\n"
                f"+ TCPDUMP container inspection successful\n"
                f"```"
                f"```Container Status:\n\n{tcpdump_output}```"
            )

    except Exception as e:
        await ctx.send(
            f"```diff\n"
            f"- EXCEPTION ERROR!\n"
            f"```"
            f"```ERROR:\n\n{str(e)}```"
        )


# get latest 5 logs from the honeypot log file
@bot.command()
async def honey_latest(ctx):
    try:
        latest_hp_logs_cmd = f"tail -n 5 {FULL_BASE_LOG_PATH}/honeypot-logs/{CONTAINER_LOG_FILE_NAME}.log"
        hp_code, hp_output, hp_error = run_ssh(latest_hp_logs_cmd)

        # print("after checking latest honeypot logs, with command:\n", latest_hp_logs_cmd)

        if hp_code != 0:
            await ctx.send(
                f"```diff\n"
                f"- HONEYPOT LOG CHECK ERROR!\n"
                f"```"
                f"```ERROR:\n\n{hp_error}```"
            )
        else:
            await ctx.send(
                f"```diff\n"
                f"+ Latest honeypot logs fetched successfully\n"
                f"```"
                f"```Latest logs:\n\n{hp_output}```"
            )

        # print("after handling checked honeypot logs")

    except Exception as e:
        await ctx.send(
            f"```diff\n"
            f"- EXCEPTION ERROR!\n"
            f"```"
            f"```ERROR:\n\n{str(e)}```"
        )



# get latest 5 logs from the current tcpdump log file
@bot.command()
async def tcp_latest(ctx):
    try:
        # command to get latest 5 log entries from the latest tcpdump file (always a .pcap file with a timestamp, given how the tcpdump container is set up):
        # (1) "cd {f'{FULL_BASE_LOG_PATH}/tcpdump-logs'}" changes directory to prepare for the next commands
        # (2) "ls -1t" lists all the files (one file per line) and sorts by time so the newest is first
        # (3) "head -n 1" gets the first file from that list (will be the latest file due to the previous 'ls' sorting by time)
        # (4) "xargs -I {} <COMMAND>" lets me take the value piped to it and use it as an argument for "<command>"
        # (5) "tcpdump -r {} -tttt -q -n" is the '<command>' that xargs' passes a result to.
        #     It reads the file it was passed ('{}' is replaced by whatever was piped to 'xargs', i.e., the latest file)
        #     and formats the output to only show timestamps, source IPs + port, and destination IPs + ports (plus protocol)
        latest_tcpdump_logs_cmd = (
            f"cd {f'{FULL_BASE_LOG_PATH}/tcpdump-logs'} "
            "&& ls -1t "
            "| head -n 1 "                                # TODO: SOMEHOW PRINT OUT THE FILENAME I END UP READING FROM AS WELL
            "| xargs -r -I {} tcpdump -r {} -tttt -q -n " # TODO: (maybe echo the xargs or head, or set it as a variable and use that for the rest of the command sequence)
            "| tail -n 5"
        )

        # print("command for latest logs is:\n", latest_tcpdump_logs_cmd)

        tcp_code, tcp_output, tcp_error = run_ssh(latest_tcpdump_logs_cmd)

        # print("after running tcpdump log check command")

        if tcp_code != 0:
            await ctx.send(
                f"```diff\n"
                f"- TCPDUMP LOG CHECK ERROR!\n"
                f"```"
                f"```ERROR:\n\n{tcp_error}```"
            )
        else:
            await ctx.send(
                f"```diff\n"
                f"+ Latest tcpdump logs fetched successfully\n"
                f"```"
                f"```Latest logs:\n\n{tcp_output}```"
            )

        # print("after handling checked tcpdump logs\n")

    except Exception as e:
        await ctx.send(
            f"```diff\n"
            f"- EXCEPTION ERROR!\n"
            f"```"
            f"```ERROR:\n\n{str(e)}```"
        )


# stop and remove the honeypot container
@bot.command()
async def honey_purge(ctx):
    try:
        stop_HP_cmd = f"docker stop {HP_CONTAINER}"
        hp_stop_code, hp_stop_output, hp_stop_error = run_ssh(stop_HP_cmd)

        if hp_stop_code != 0:
            await ctx.send(
                f"```diff\n"
                f"- HONEYPOT CONTAINER STOP ERROR!\n"
                f"```"
                f"```ERROR:\n\n{hp_stop_error}```"
            )
        else:
            await ctx.send(
                f"```diff\n"
                f"+ Honeypot container stopped successfully\n"
                f"```"
            )

        rm_HP_cmd = f"docker rm {HP_CONTAINER}"
        hp_rm_code, hp_rm_output, hp_rm_error = run_ssh(rm_HP_cmd)

        if hp_rm_code != 0:
            await ctx.send(
                f"```diff\n"
                f"- HONEYPOT CONTAINER REMOVE ERROR!\n"
                f"```"
                f"```ERROR:\n\n{hp_rm_error}```"
            )
        else:
            await ctx.send(
                f"```diff\n"
                f"+ Honeypot container removed successfully\n"
                f"```"
            )

    except Exception as e:
        await ctx.send(
            f"```diff\n"
            f"- EXCEPTION ERROR!\n"
            f"```"
            f"```ERROR:\n\n{str(e)}```"
        )


# stop and remove the tcpdump container
@bot.command()
async def tcp_purge(ctx):
    try:
        stop_TCP_cmd = f"docker stop {TCPDUMP_CONTAINER}"
        tcp_stop_code, tcp_stop_output, tcp_stop_error = run_ssh(stop_TCP_cmd)

        if tcp_stop_code != 0:
            await ctx.send(
                f"```diff\n"
                f"- TCPDUMP CONTAINER STOP ERROR!\n"
                f"```"
                f"```ERROR:\n\n{tcp_stop_error}```"
            )
        else:
            await ctx.send(
                f"```diff\n"
                f"+ Tcpdump container stopped successfully\n"
                f"```"
            )

        rm_TCP_cmd = f"docker rm {TCPDUMP_CONTAINER}"
        tcp_rm_code, tcp_rm_output, tcp_rm_error = run_ssh(rm_TCP_cmd)

        if tcp_rm_code != 0:
            await ctx.send(
                f"```diff\n"
                f"- TCPDUMP CONTAINER REMOVE ERROR!\n"
                f"```"
                f"```ERROR:\n\n{tcp_rm_error}```"
            )
        else:
            await ctx.send(
                f"```diff\n"
                f"+ Tcpdump container removed successfully\n"
                f"```"
            )

    except Exception as e:
        await ctx.send(
            f"```diff\n"
            f"- EXCEPTION ERROR!\n"
            f"```"
            f"```ERROR:\n\n{str(e)}```"
        )



# command to handle log fetching:
# (1) check if tcpdump container is running in the first place
# (2) forcibly stop container(s),
# (3) secure-copy the logs to the local machine,
# (4) delete logs from the instance, 
# (5) recreate container(s) (only recreate tcpdump container if it was originally running!))
@bot.command()
async def fetch(ctx):
    try:
        # first, check if tcpdump container is even running in the first place:
        tcpdump_running = False
        check_tcpdump_cmd = f"docker container inspect -f '{{{{.State.Status}}}}' {TCPDUMP_CONTAINER}"
        tcpdump_code, tcpdump_output, tcpdump_error = run_ssh(check_tcpdump_cmd)

        if "no such container" not in tcpdump_error.lower():
            tcpdump_running = True

        # print("tcpdump_running: ", tcpdump_running)

        # force stop container(s) (they get created/run with "--rm" so this should effeectively auto-remove them):
        stop_HP_cmd = f"docker stop {HP_CONTAINER} 2>/dev/null || true"
        stop_TCPDUMP_cmd = f"docker stop {TCPDUMP_CONTAINER} 2>/dev/null || true"
        run_ssh(stop_HP_cmd)
        run_ssh(stop_TCPDUMP_cmd)

        # print("stopped containers")

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file_name = f"{CONTAINER_LOG_FILE_NAME}_{timestamp}-{cloud_platform}.json" # ".json" converts the ".log" file to a JSON file, and the cloud platform is appended to more easily identify log entry origin

        remote_file = f"{FULL_BASE_LOG_PATH}/honeypot-logs/{CONTAINER_LOG_FILE_NAME}.log"
        local_file = f"{HOST_LOG_DIR}\\hp_logs\\{log_file_name}"

        hp_logs_copied = False

        try:
            # this doesn't return anything, but it raises an exception on failure
            transfer_file(remote_file, local_file)

            if not Path(local_file).exists():
                await ctx.send(
                    f"```diff\n"
                    f"- ERROR LOCATING COPIED HONEYPOT LOG AFTER TRANSFER!\n"
                    f"```"
                )
            else:
                hp_logs_copied = True
                await ctx.send(
                    f"```ini\n"
                    f"[Honeypot logs fetched]\n"
                    f"```"
                )

        except Exception as e:
            await ctx.send(
                f"```diff\n"
                f"- ERROR FETCHING HONEYPOT LOGS VIA SFTP!\n"
                f"```"
                f"```ERROR:\n\n{str(e)}```"
            )

        # check for errors with secure-copying the logs
        if hp_logs_copied:

            # ONLY DELETE LOGS IF FETCHING WAS SUCCESSFUL
            # delete all the logs that were just successfully copied
            # ? Note, the honeypot log file is not deleted, only cleared, so that the folder will never be empty!
            purge_logs = f"truncate -s 0 {FULL_BASE_LOG_PATH}/honeypot-logs/{CONTAINER_LOG_FILE_NAME}.log"
            hp_log_purge_code, hp_log_purge_output, hp_log_purge_error = run_ssh(purge_logs)

            # verify successful log deletion
            if hp_log_purge_code != 0:
                await ctx.send(
                    f"```diff\n"
                    f"- HONEYPOT LOG DELETION ERROR!\n"
                    f"```"
                    f"```ERROR:\n\n{hp_log_purge_error}```"
                )
            else:
                await ctx.send(
                    f"```ini\n"
                    f"[Honeypot log deletion successful]\n"
                    f"```"
                    f"```Container Status:\n\n{hp_log_purge_output}```"
                )

        tcp_logs_copied = False

        try:
            remote_dir = f"{FULL_BASE_LOG_PATH}/tcpdump-logs"
            local_dir = f"{HOST_LOG_DIR}\\tcp_logs"

            # this function *DOES* return something,
            # namely the status codes of a tar extraction command and a subsequent archive removal command.
            # It also raises an exception on failure
            tar_exit_code, archive_removal_exit_code = transfer_files_from_dir(remote_dir, local_dir)

            if tar_exit_code != 0:
                await ctx.send(
                    "```diff\n"
                    "- TAR COMMAND TO UNZIP EXTRACTD ARCHIVE FAILED!\n"
                    "```"
                )
            elif archive_removal_exit_code != 0:
                await ctx.send(
                    "```diff\n"
                    "- REMOVAL OF EXTRACTED ARCHIVE FAILED!\n"
                    "```"
                )
            else:
                tcp_logs_copied = True
                await ctx.send(
                    f"```ini\n"
                    f"[TCPDUMP logs fetched]\n"
                    f"```"
                )

        except Exception as e:
            await ctx.send(
                f"```diff\n"
                f"- ERROR FETCHING TCPDUMP LOGS VIA SFTP!\n"
                f"```"
                f"```ERROR:\n\n{str(e)}```"
            )

        # check for errors with secure-copying the logs
        if tcp_logs_copied:

            # ONLY DELETE LOGS IF FETCHING WAS SUCCESSFUL
            # delete all the logs that were just successfully copied
            # ? Note, the honeypot log file is not deleted, only cleared, so that the folder will never be empty!
            purge_logs = f"rm {FULL_BASE_LOG_PATH}/tcpdump-logs/*"
            tcpdump_log_purge_code, tcpdump_log_purge_output, tcpdump_log_purge_error = run_ssh(purge_logs)

            # verify successful log deletion
            if tcpdump_log_purge_code != 0:
                await ctx.send(
                    f"```diff\n"
                    f"- TCPDUMP LOG DELETION ERROR!\n"
                    f"```"
                    f"```ERROR:\n\n{tcpdump_log_purge_error}```"
                )
            else:
                await ctx.send(
                    f"```ini\n"
                    f"[TCPDUMP log deletion successful]\n"
                    f"```"
                    f"```Container Status:\n\n{tcpdump_log_purge_output}```"
                )

        # print("after log fetching and possibly purging")

        # forcibly remove the honeypot container before trying to recreate it
        remove_HP_cmd = f"docker rm -f {HP_CONTAINER} 2>/dev/null || true"
        run_ssh(remove_HP_cmd)

        # recreate the container after logs have been fetched and deleted
        hp_code, hp_output, hp_error = run_ssh(recreate_hp_cmd)

        # print("recreated tcpdump container")

        # check for errors with recreating honeypot container
        if hp_code != 0:
            # await ctx.send(f"```diff\n# HP run_ssh ERROR:```\n```{HP_error}```")
            await ctx.send(
                f"```diff\n"
                f"- HONEYPOT CONTAINER RECREATION ERROR!\n"
                f"```"
                f"```ERROR:\n\n{hp_error}```"
            )
        else:
            # await ctx.send(f"HP inspect Successful:\n```Container Status: {HP_output}```")
            await ctx.send(
                f"```diff\n"
                f"+ Honeypot container successfully recreated\n"
                f"```"
                f"```Container Status:\n\n{hp_output}```"
            )

        # print("after tcpdump container recreation")

        # only recreate tcpdump container if it was running before:
        if tcpdump_running:
            # forcibly remove the tcpdump container before trying to recreate it
            remove_TCPDUMP_cmd = f"docker rm -f {TCPDUMP_CONTAINER} 2>/dev/null || true"
            run_ssh(remove_TCPDUMP_cmd)

            # recreate the container after logs have been fetched and deleted
            tcpdump_code, tcpdump_output, tcpdump_error = run_ssh(recreate_tcpdump_cmd)

            # check for errors with recreating tcpdump container
            if tcpdump_code != 0:
                await ctx.send(
                    f"```diff\n"
                    f"- TCPDUMP CONTAINER RECREATION ERROR!\n"
                    f"```"
                    f"```ERROR:\n\n{tcpdump_error}```"
                )
            else:
                # await ctx.send(f"```diff\nTCPDUMP inspect Successful:```\n```Container Status: {TCPDUMP_output}```")
                await ctx.send(
                    f"```diff\n"
                    f"+ TCPDUMP container successfully recreated\n"
                    f"```"
                    f"```Container Status:\n\n{tcpdump_output}```"
                )

        # print("after checking and possibly recreating tcpdump container")

    except Exception as e:
        await ctx.send(
            f"```diff\n"
            f"- EXCEPTION ERROR!\n"
            f"```"
            f"```ERROR:\n\n{str(e)}```"
        )


# start the bot!
bot.run(TOKEN)