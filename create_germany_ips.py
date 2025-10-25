import csv
import ipaddress
import zipfile
import shutil
import subprocess
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# --- Config ---
BASE_URL = "https://download.ip2location.com/lite"
ZIP_V4   = "IP2LOCATION-LITE-DB1.CSV.ZIP"
ZIP_V6   = "IP2LOCATION-LITE-DB1.IPV6.CSV.ZIP"
CSV_V4   = "IP2LOCATION-LITE-DB1.CSV"
CSV_V6   = "IP2LOCATION-LITE-DB1.IPV6.CSV"
OUTPUT   = Path("germany_ips.caddy")
TRY_CADDY_RELOAD = True

def download(url: str, dest: Path):
    print(f"Downloading {url} …")
    req = Request(url, headers={"User-Agent": "ip2loc-lite-fetch/1.0"})
    try:
        with urlopen(req, timeout=120) as r, dest.open("wb") as f:
            shutil.copyfileobj(r, f)
    except HTTPError as e:
        raise SystemExit(f"HTTP error downloading {url}: {e.code} {e.reason}")
    except URLError as e:
        raise SystemExit(f"URL error downloading {url}: {e.reason}")
    print(f"Saved → {dest}")

def unzip(zip_path: Path, expected_member: str, out_dir: Path):
    print(f"Extracting {zip_path} …")
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        member = None
        # try exact, else any that endswith expected
        if expected_member in names:
            member = expected_member
        else:
            for n in names:
                if n.lower().endswith(expected_member.lower()):
                    member = n
                    break
        if not member:
            raise SystemExit(f"{expected_member} not found in {zip_path}. Members: {names}")
        zf.extract(member, path=out_dir)
        extracted = out_dir / member
        final_path = out_dir / expected_member
        if extracted != final_path:
            if final_path.exists():
                final_path.unlink()
            extracted.rename(final_path)
    print(f"Extracted → {out_dir/expected_member}")

def csv_rows(path: Path):
    # Works for headerless or headered CSV, with quotes and spaces after commas
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.reader(f, delimiter=",", quotechar='"', skipinitialspace=True)
        first = next(rdr, None)
        if first is None:
            return  # empty
        # Detect header: first cell is non-numeric (e.g. 'ip_from') → skip it
        def is_int(s):
            try:
                int(s)
                return True
            except:  # noqa: E722
                return False
        if not is_int(first[0]):
            # header case; continue with remaining rows
            for row in rdr:
                yield row
        else:
            # no header; include first row
            yield first
            for row in rdr:
                yield row

def read_germany_cidrs_v4(p: Path):
    cidrs = []
    for row in csv_rows(p):
        if len(row) < 4:
            continue
        ip_from, ip_to, country_code, country_name = row[0], row[1], row[2], row[3]
        if country_name != "Germany":
            continue
        s = ipaddress.IPv4Address(int(ip_from))
        e = ipaddress.IPv4Address(int(ip_to))
        cidrs.extend(ipaddress.summarize_address_range(s, e))
    return cidrs

def read_germany_cidrs_v6(p: Path):
    cidrs = []
    for row in csv_rows(p):
        if len(row) < 4:
            continue
        ip_from, ip_to, country_code, country_name = row[0], row[1], row[2], row[3]
        if country_name != "Germany":
            continue
        s = ipaddress.IPv6Address(int(ip_from))
        e = ipaddress.IPv6Address(int(ip_to))
        cidrs.extend(ipaddress.summarize_address_range(s, e))
    return cidrs

def write_caddy_remote_ip(nets, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("remote_ip " + " ".join(str(n) for n in nets) + "\n")
    print(f"Wrote {len(nets)} CIDRs → {out_path}")

def maybe_reload_caddy():
    if not TRY_CADDY_RELOAD:
        return
    try:
        print("Reloading caddy …")
        subprocess.run(
            ["docker", "compose", "restart", "caddy"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        print("caddy reload: OK")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Skipping caddy reload (not installed or failed): {e}")

def main():
    workdir = Path.cwd()
    zip_v4_path = workdir / ZIP_V4
    zip_v6_path = workdir / ZIP_V6

    download(f"{BASE_URL}/{ZIP_V4}", zip_v4_path)
    download(f"{BASE_URL}/{ZIP_V6}", zip_v6_path)

    unzip(zip_v4_path, CSV_V4, workdir)
    unzip(zip_v6_path, CSV_V6, workdir)

    print("Parsing IPv4 CSV …")
    v4 = read_germany_cidrs_v4(workdir / CSV_V4)
    print(f"  → {len(v4)} IPv4 chunks before collapse")

    print("Parsing IPv6 CSV …")
    v6 = read_germany_cidrs_v6(workdir / CSV_V6)
    print(f"  → {len(v6)} IPv6 chunks before collapse")

    all_nets_v4 = list(ipaddress.collapse_addresses(v4))
    all_nets_v6 = list(ipaddress.collapse_addresses(v6))
    ## all_nets.sort(key=lambda n: (n.version, int(n.network_address), n.prefixlen))
    all_nets = all_nets_v4 + all_nets_v6
    if len(all_nets) > 10000:
        write_caddy_remote_ip(all_nets, OUTPUT)
        # reloading caddy is within here and not .sh so that it does not get reloaded unnecessarily
        maybe_reload_caddy()
    else:
        print(f"len(all_nets) is too small with {len(all_nets)}. Therefore file does not get updated. And caddy not relaoded.")
    print("Done.")

if __name__ == "__main__":
    main()
