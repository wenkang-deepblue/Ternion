# Public Tunnel Configuration Guide

This document explains how to expose a local Ternion service to the public internet by using `ngrok` as an example.

The goal is:

1. Run Ternion locally.
2. Use `ngrok` to create a public HTTPS tunnel to your local Ternion backend.
3. Use the generated public URL in Cursor's `Override OpenAI Base URL`.

## 1. Important Notes

- Cursor does not accept `localhost` or `127.0.0.1` for `Override OpenAI Base URL`.
- Ternion runs locally by default, so you need a publicly reachable HTTPS URL before Cursor can connect to it.
- `ngrok` is a third-party service. You must register your own account and comply with ngrok's terms and limits.
- According to ngrok's current official quickstart, you need:
  - an ngrok account
  - an ngrok auth token
  - the ngrok Agent CLI installed on your machine

Official references:

- [ngrok Agent CLI Quickstart](https://ngrok.com/docs/getting-started)
- [ngrok Download Page](https://ngrok.com/download/)
- [ngrok HTTP Documentation](https://ngrok.com/docs/http)

## 2. Prerequisites

Before configuring the tunnel, make sure:

1. Ternion is installed.
2. You can start Ternion locally with:

```bash
ternion
```

3. You know which local backend port Ternion is using.

By default, Ternion uses backend port `9110`, but if you changed it during first-run initialization, use your actual configured backend port instead.

## 3. Create an ngrok Account

According to ngrok's official quickstart, you must create an ngrok account before using the agent.

1. Open the ngrok signup page:
   [https://dashboard.ngrok.com/signup](https://dashboard.ngrok.com/signup)
2. Register an account.
3. Sign in to the ngrok dashboard.

After you sign in, you will need your auth token from the dashboard.

## 4. Get Your ngrok Auth Token

The ngrok official quickstart requires you to connect the local ngrok agent to your account by adding your auth token.

You can get the token from:

- [https://dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken)

Keep this token private.

## 5. Install the ngrok Agent CLI

Use an installation method that matches your operating system.

### macOS

The official quickstart recommends Homebrew:

```bash
brew install ngrok
```

### Debian / Ubuntu

The official quickstart provides the following installation flow:

```bash
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
  && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list \
  && sudo apt update \
  && sudo apt install ngrok
```

### Windows

The official download page lists these options:

1. Install from the Microsoft Store
2. Install via WinGet
3. Install via Scoop
4. Use the direct download page

Official download page:

- [https://ngrok.com/download/](https://ngrok.com/download/)

### Verify the installation

After installation, run:

```bash
ngrok help
```

If the command prints ngrok help text, the agent is installed correctly.

## 6. Connect the Local ngrok Agent to Your Account

After installation, add your auth token.

Replace `<YOUR_TOKEN>` with the token copied from the ngrok dashboard:

```bash
ngrok config add-authtoken <YOUR_TOKEN>
```

This step is required by ngrok's official quickstart so the local agent can connect to your ngrok account.

## 7. Start Ternion Locally

Start Ternion in your terminal:

```bash
ternion
```

When Ternion starts, confirm the backend URL shown in the CLI output. For example:

```text
Local API:      http://127.0.0.1:9110/v1
Control Panel:  http://127.0.0.1:9110/panel
API Docs:       http://127.0.0.1:9110/docs
```

If your configured backend port is not `9110`, replace `9110` in all following `ngrok` examples with your actual backend port.

## 8. Start the ngrok HTTP Tunnel

Once Ternion is already listening locally, open another terminal and run:

```bash
ngrok http 9110
```

If your Ternion backend uses a different port, replace `9110` with that port.

According to ngrok's official quickstart:

- free accounts receive an automatically chosen development domain
- paid plans can use the optional `--url` flag to customize the domain

Example with a custom port:

```bash
ngrok http 9456
```

The ngrok agent should display a console UI in the terminal and show a public forwarding URL.

That forwarding URL is the HTTPS address that points to your local Ternion backend.

## 9. Copy the Public HTTPS URL

After `ngrok http <backend-port>` starts successfully, ngrok will provide a public HTTPS URL such as:

```text
https://example-name.ngrok.app
```

Use the HTTPS root URL exactly as shown by ngrok.

For Ternion and Cursor integration:

- use the public HTTPS root URL
- do not replace it with `localhost`
- do not use the local `127.0.0.1` address in Cursor
- if Ternion's Control Panel shows a copyable Cursor Base URL, prefer copying that value directly

## 10. Use the URL in Cursor

Open Cursor and go to:

`Settings -> Models -> API Keys`

Then configure the OpenAI-compatible endpoint flow:

1. Turn on `Override OpenAI Base URL`.
2. Paste the public HTTPS URL generated by ngrok.
3. Turn on the `OpenAI API Key` section if your Cursor setup requires it.
4. Enter any placeholder text if your current Cursor workflow accepts a placeholder key for the OpenAI-compatible endpoint.
5. Make sure `ternion-team` is available in your model list if your setup requires adding the custom model manually.

If your current Ternion Control Panel instructions say not to append `/v1`, follow the Control Panel guidance shown by your installed version.

## 11. Confirm That the Tunnel Works

After configuring Cursor:

1. Keep the `ternion` terminal running.
2. Keep the `ngrok` terminal running.
3. Send a simple request from Cursor to the Ternion model.
4. Confirm Ternion receives and processes the request successfully.

You can also test the public URL in a browser first if you want to confirm the tunnel is live.

## 12. Common Mistakes

### 1. Ternion is not running before `ngrok http`

If Ternion is not already listening on the backend port, the tunnel will not forward requests correctly.

Always start `ternion` first.

### 2. Wrong local port

If you changed Ternion's backend port during initialization, `ngrok http 9110` may be wrong.

Use your actual configured backend port.

### 3. Auth token not configured

If you installed ngrok but did not run:

```bash
ngrok config add-authtoken <YOUR_TOKEN>
```

the local agent may fail to connect to your account.

### 4. Using a local URL in Cursor

`http://127.0.0.1:9110` is only for local machine access.

Cursor needs the public HTTPS URL provided by the tunnel.

### 5. Closing the ngrok terminal

The public URL only stays active while the ngrok process is still running.

If you stop ngrok, the tunnel will stop working.

## 13. Optional Security and Advanced Configuration

The ngrok official quickstart also documents more advanced options, such as:

- editing the ngrok config with `ngrok config edit`
- defining named endpoints
- applying traffic policies
- adding authentication in front of your local app

If you need advanced controls, continue from the official quickstart:

- [https://ngrok.com/docs/getting-started](https://ngrok.com/docs/getting-started)

## 14. Summary

The minimal working flow is:

```bash
ternion
ngrok config add-authtoken <YOUR_TOKEN>
ngrok http 9110
```

Then:

1. copy the HTTPS URL printed by ngrok
2. paste it into Cursor's `Override OpenAI Base URL` according to the guidance shown by Ternion
3. keep both the Ternion process and the ngrok process running

If your backend port is not `9110`, replace it with your actual configured port.
