"""Commands for managing Two-Factor Authentication (2FA)."""

import json
import argparse

import requests

from vast_cli.parser import parser, argument
from vast_cli import state
from vast_cli.api.client import http_get, http_post, http_put, http_del
from vast_cli.api.helpers import apiurl, apiheaders
from vast_cli.display.formatting import deindent
from vast_cli.helpers import (
    handle_failed_tfa_verification,
    format_backup_codes,
    confirm_destructive_action,
    save_to_file,
    get_backup_codes_filename,
    save_backup_codes,
    build_tfa_verification_payload,
)
from vast_cli.display.rich_tables import display_tfa_methods, TFA_METHOD_FIELDS
from vast_cli.config import TFAKEY_FILE, APIKEY_FILE, SUCCESS, WARN, FAIL, INFO


@parser.command(
    argument("code", help="6-digit verification code from SMS or Authenticator app", type=str),
    argument("--sms", help="Use SMS 2FA method instead of TOTP", action="store_true"),
    argument("--secret", help="Secret token from setup process (required)", type=str, required=True),
    argument("--phone-number", help="Phone number for SMS method (E.164 format)", type=str, default=None),
    argument("-l", "--label", help="Label for the new 2FA method", type=str, default=None),
    usage="vastai tfa activate CODE --secret SECRET [--sms] [--phone-number PHONE_NUMBER] [--label LABEL]",
    help="Activate a new 2FA method by verifying the code",
    epilog=deindent("""
        Complete the 2FA setup process by verifying your code.

        For TOTP (Authenticator app):
         1. Run 'vastai tfa totp-setup' to get the manual key/QR code and secret
         2. Enter the manual key or scan the QR code with your Authenticator app
         3. Run this command with the 6-digit code from your app and the secret token from step 1

        For SMS:
         1. Run 'vastai tfa send-sms --phone-number <PHONE_NUMBER>' to receive SMS and get secret token
         2. Run this command with the code you received via SMS and the phone number it was sent to

        If this is your first 2FA method, backup codes will be generated and displayed.
        Save these backup codes in a secure location!

        Examples:
         vastai tfa activate --secret abc123def456 123456
         vastai tfa activate --secret abc123def456 --phone-number +12345678901 123456
         vastai tfa activate --secret abc123def456 --phone-number +12345678901 --label "Work Phone" 123456
    """),
)
def tfa__activate(args):
    """Activate a new 2FA method by confirming the verification code."""
    url = apiurl(args, "/api/v0/tfa/test-submit/")

    # Build the request payload
    payload = build_tfa_verification_payload(args, phone_number=args.phone_number, label=args.label)

    r = http_post(args, url, headers=apiheaders(args), json=payload)
    r.raise_for_status()

    response_data = r.json()

    # Display success message
    method_name = "SMS" if args.phone_number or args.sms else "TOTP (Authenticator App)"
    print(f"\n{SUCCESS} {method_name} 2FA method activated successfully!")

    # Display backup codes if this is the first 2FA method
    if "backup_codes" in response_data:
        save_backup_codes(response_data["backup_codes"])


@parser.command(
    argument("-id", "--id-to-delete", help="ID of the 2FA method to delete (see `vastai tfa status`)", type=int, default=None),
    argument("-c", "--code", mutex_group='code_grp', required=True, help="2FA code from your Authenticator app or SMS to authorize deletion", type=str),
    argument("--sms", mutex_group="type_grp", help="Use SMS 2FA method instead of TOTP", action="store_true"),
    argument("-s", "--secret", help="Secret token (required for SMS authorization)", type=str, default=None),
    argument("-bc", "--backup-code", mutex_group='code_grp', required=True, help="One-time backup code (alternative to regular 2FA code)", type=str, default=None),
    argument("--method-id", help="2FA Method ID if you have more than one of the same type ('id' from `tfa status`)", type=str, default=None),
    usage="vastai tfa delete [--id-to-delete ID] [--code CODE] [--sms] [--secret SECRET] [--backup-code BACKUP_CODE] [--method-id ID]",
    help="Remove a 2FA method from your account",
    epilog=deindent(f"""
        Remove a 2FA method from your account.

        This action requires 2FA verification to prevent unauthorized removals.

        {'*'*120}
        NOTE: If you do not specify --id-to-delete, the system will attempt to delete the method you are using to authenticate.
              However please be advised, it is much safer to specify the ID to avoid confusion if you have multiple methods.
        {'*'*120}

           Use `vastai tfa status` to see your active methods and their IDs.

        Examples:
         # Delete method #123, authorize with TOTP/Authenticator code
         vastai tfa delete --id-to-delete 123 --code 456789

         # Delete method #123, authorize with SMS and secret from `tfa send-sms`
         vastai tfa delete -id 123 --sms --secret abc123def456 -c 456789

         # Delete method #123, authorize with backup code
         vastai tfa delete --id-to-delete 123 --backup-code ABCD-EFGH-IJKL

         # Delete method #123, specify which TOTP method to use if you have multiple
         vastai tfa delete -id 123 --method-id 456 -c 456789

         # Delete the TOTP method you are using to authenticate (use with caution)
         vastai tfa delete -c 456789
    """),
)
def tfa__delete(args):
    """Remove a 2FA method from the user's account after verifying authorization."""
    url = apiurl(args, "/api/v0/tfa/")

    if args.sms and not args.secret:
        print(f"\n{FAIL} Error: --secret is required for deletion authorization when using --sms.")
        print("\nPlease use:  `vastai tfa send-sms` to get the missing secret and try again.")
        return 1

    # Confirm action since this invalidates existing codes
    prompt = "\nAre you sure you want to delete this 2FA method? (y|n): "
    if confirm_destructive_action(prompt) == False:
        print("Operation cancelled.")
        return

    # Build the request payload
    payload = build_tfa_verification_payload(args, target_id=args.id_to_delete)
    try:
        r = http_del(args, url, headers=apiheaders(args), json=payload)
        r.raise_for_status()

        response_data = r.json()

        print(f"\n{SUCCESS} 2FA method deleted successfully.")

        if "remaining_methods" in response_data:
            remaining = response_data["remaining_methods"]
            print(f"\nYou have {remaining} 2FA method{'s' if remaining != 1 else ''} remaining.")
        else:
            print(f"\n{WARN}  WARNING: You have removed all 2FA methods from your account.")
            print("Your backup codes have been invalidated and 2FA is now fully disabled.")

    except requests.exceptions.HTTPError as e:
        handle_failed_tfa_verification(args, e)
        return 1


@parser.command(
    argument("-c", "--code", mutex_group='code_grp', required=True, help="2FA code from Authenticator app (default) or SMS", type=str),
    argument("--sms", mutex_group="type_grp", help="Use SMS 2FA method instead of TOTP", action="store_true"),
    argument("-s", "--secret", help="Secret token from previous login step (required for SMS)", type=str, default=None),
    argument("-bc", "--backup-code", mutex_group='code_grp', required=True, help="One-time backup code (alternative to regular 2FA code)", type=str, default=None),
    argument("-id", "--method-id", mutex_group="type_grp", help="2FA Method ID if you have more than one of the same type ('id' from `tfa status`)", type=str, default=None),

    usage="vastai tfa login [--code CODE] [--sms] [--secret SECRET] [--backup-code BACKUP_CODE]",
    help="Complete 2FA login by verifying code",
    epilog=deindent("""
        Complete Two-Factor Authentication login by providing the 2FA code.

        For TOTP (default): Provide the 6-digit code from your Authenticator app
        For SMS: Include the --sms flag and provide -s/--secret from the `tfa send-sms` command response
        For backup code: Use --backup-code instead of code (codes may only be used once)

        Examples:
         vastai tfa login -c 123456
         vastai tfa login --code 123456 --sms --secret abc123def456
         vastai tfa login --backup-code ABCD-EFGH-IJKL

    """),
)
def tfa__login(args):
    """Complete 2FA login and store the session key."""
    url = apiurl(args, "/api/v0/tfa/")

    # Build the request payload
    payload = build_tfa_verification_payload(args)

    try:
        r = http_post(args, url, headers=apiheaders(args), json=payload)
        r.raise_for_status()

        response_data = r.json()

        # Check for session_key in response and save it
        if "session_key" in response_data:
            session_key = response_data["session_key"]
            if session_key != args.api_key:
                # Write the session key to the TFA key file
                with open(TFAKEY_FILE, "w") as f:
                    f.write(session_key)
                print(f"{SUCCESS} 2FA login successful! Session key saved to {TFAKEY_FILE}")
            else:
                print(f"{SUCCESS} 2FA login successful! Your session key has been refreshed.")

            # Display remaining backup codes if present
            if "backup_codes_remaining" in response_data:
                remaining = response_data["backup_codes_remaining"]
                if remaining == 0:
                    print(f"{WARN}  Warning: You have no backup codes remaining! Please generate new backup codes immediately to avoid being locked out of your account if you lose access to your 2FA device.")
                elif remaining <= 3:
                    print(f"{WARN}  Warning: You only have {remaining} backup codes remaining. Consider regenerating them.")
                else:
                    print(f"Backup codes remaining: {remaining}")
        else:
            print("2FA login successful but a session key was not returned. Please check that you have an API Key that's properly set up")

    except requests.exceptions.HTTPError as e:
        handle_failed_tfa_verification(args, e)
        return 1


@parser.command(
    argument("-p", "--phone-number", help="Phone number to receive SMS code (E.164 format, e.g., +1234567890)", type=str, default=None),
    argument("-s", "--secret", help="Secret token from the original 2FA login attempt", type=str, required=True),
    usage="vastai tfa resend-sms --secret SECRET [--phone-number PHONE_NUMBER]",
    help="Resend SMS 2FA code",
    epilog=deindent("""
        Resend the SMS verification code to your phone.

        This is useful if:
        • You didn't receive the original SMS
        • The code expired before you could use it
        • You accidentally deleted the message

        You must provide the same secret token from the original request.

        Example:
         vastai tfa resend-sms --secret abc123def456
    """),
)
def tfa__resend_sms(args):
    """Resend SMS 2FA code to the user's phone."""
    url = apiurl(args, "/api/v0/tfa/resend/")
    payload = build_tfa_verification_payload(args, phone_number=args.phone_number)

    r = http_post(args, url, headers=apiheaders(args), json=payload)
    r.raise_for_status()

    response_data = r.json()

    print(f"{SUCCESS} SMS code resent successfully!")
    print(f"\n{response_data['msg']}")
    print(f"\nOnce you receive the SMS code, complete your 2FA login with:")
    print(f"  vastai tfa login --sms --secret {args.secret} -c <CODE>")


@parser.command(
    argument("-c", "--code", mutex_group='code_grp', required=True, help="2FA code from Authenticator app (default) or SMS", type=str),
    argument("--sms", mutex_group="type_grp", help="Use SMS 2FA method instead of TOTP", action="store_true"),
    argument("-s", "--secret", help="Secret token from previous login step (required for SMS)", type=str, default=None),
    argument("-bc", "--backup-code", mutex_group='code_grp', required=True, help="One-time backup code (alternative to regular 2FA code)", type=str, default=None),
    argument("-id", "--method-id", mutex_group="type_grp", help="2FA Method ID if you have more than one of the same type ('id' from `tfa status`)", type=str, default=None),
    usage="vastai tfa regen-codes [--code CODE] [--sms] [--secret SECRET] [--backup-code BACKUP_CODE] [--method-id ID]",
    help="Regenerate backup codes for 2FA",
    epilog=deindent("""
        Generate a new set of backup codes for your account.

        This action requires 2FA verification to prevent unauthorized regeneration.

        WARNING: This will invalidate all existing backup codes!
        Any previously generated codes will no longer work.

        Backup codes are one-time use codes that allow you to log in
        if you lose access to your primary 2FA method (lost phone, etc).

        You should regenerate your backup codes if:
        • You've used several codes and are running low
        • You think your codes may have been compromised
        • You lost your saved codes and need new ones

        Important: Save the new codes in a secure location immediately!
        They will not be shown again.

        Examples:
         vastai tfa regen-codes --code 123456
         vastai tfa regen-codes -c 123456 --sms --secret abc123def456
         vastai tfa regen-codes --backup-code ABCD-EFGH-IJKL
    """),
)
def tfa__regen_codes(args):
    """Regenerate backup codes for 2FA recovery."""
    url = apiurl(args, "/api/v0/tfa/regen-backup-codes/")

    # Confirm action since this invalidates existing codes
    prompt = "\nThis will invalidate all existing backup codes. Continue? (y|n): "
    if confirm_destructive_action(prompt) == False:
        print("Operation cancelled.")
        return

    # Build the request payload with verification
    payload = build_tfa_verification_payload(args)
    try:
        r = http_put(args, url, headers=apiheaders(args), json=payload)
        r.raise_for_status()

        response_data = r.json()

        # Display the new backup codes
        if "backup_codes" in response_data:
            save_backup_codes(response_data["backup_codes"])
        else:
            print(f"\n{SUCCESS} Backup codes regenerated successfully!")
            print("(No codes returned in response - this may be an error)")

    except requests.exceptions.HTTPError as e:
        handle_failed_tfa_verification(args, e)
        return 1


@parser.command(
    argument("-p", "--phone-number", help="Phone number to receive SMS code (E.164 format, e.g., +1234567890)", type=str, default=None),
    usage="vastai tfa send-sms [--phone-number PHONE_NUMBER]",
    help="Request a 2FA SMS verification code",
    epilog=deindent("""
        Request a two-factor authentication code to be sent via SMS.

        If --phone-number is not provided, uses the phone number on your account.
        The secret token will be returned and must be used with 'vastai tfa activate'.

        Examples:
         vastai tfa send-sms
         vastai tfa send-sms --phone-number +12345678901
    """),
)
def tfa__send_sms(args):
    """Request a 2FA SMS code to be sent to the user's phone."""
    url = apiurl(args, "/api/v0/tfa/test/")

    # Build the request payload
    payload = {}

    # Add phone number if provided
    if args.phone_number:
        payload["phone_number"] = args.phone_number

    r = http_post(args, url, headers=apiheaders(args), json=payload)
    r.raise_for_status()

    response_data = r.json()

    # Extract and display the secret token
    secret = response_data["secret"]
    print(f"{SUCCESS} SMS code sent successfully!")
    print(f"  Secret token: {secret}")
    print(f"\nOnce you receive the SMS code:")
    print(f"\n  If you are setting up SMS 2FA for the first time, run:")
    phone_num = f"--phone-number {args.phone_number}" if args.phone_number else "[--phone-number <PHONE_NUMBER>]"
    print(f"    vastai tfa activate --sms --secret {secret} {phone_num} [--label <LABEL>] <CODE>")
    print(f"\n  Otherwise you can complete your 2FA log in with:")
    print(f"    vastai tfa login --sms --secret {secret} -c <CODE>\n")


@parser.command(
    help="Shows the current 2FA status and configured methods",
    epilog=deindent("""
        Show the current 2FA status for your account, including:
         • Whether or not 2FA is enabled
         • A list of active 2FA methods
         • The number of backup codes remaining (if 2FA is enabled)
    """)
)
def tfa__status(args):
    """Show the current 2FA status for the user."""
    url = apiurl(args, "/tfa/status/")
    r = http_get(args, url)
    r.raise_for_status()
    response_data = r.json()

    if args.raw:
        print(json.dumps(response_data, indent=2))
        return

    tfa_enabled = response_data.get("tfa_enabled", False)
    methods = response_data.get("methods", [])
    backup_codes_remaining = response_data.get("backup_codes_remaining", 0)

    if not tfa_enabled or not methods:
        print(f"{WARN}  No active 2FA methods found")
    else:
        print(f"2FA Status: Enabled {SUCCESS}")
        print(f"\nActive 2FA Methods:")
        display_tfa_methods(methods)
        print(f"\nBackup codes remaining: {backup_codes_remaining}")


@parser.command(
    usage="vastai tfa totp-setup",
    help="Generate TOTP secret and QR code for Authenticator app setup",
    epilog=deindent("""
        Set up TOTP (Time-based One-Time Password) 2FA using an Authenticator app.

        This command generates a new TOTP secret and displays:
        • A QR code (for scanning with your app)
        • A manual entry key (for typing into your app)
        • A secret token (needed for the next step)

        Workflow:
         1. Run this command to generate the TOTP secret
         2. Add the account to your Authenticator app by either:
            • Scanning the displayed QR code, OR
            • Manually entering the key shown
         3. Once added, your app will display a 6-digit code
         4. Complete setup by running:
            vastai tfa activate --secret <SECRET> <CODE>

        Supported Authenticator Apps:
         • Google Authenticator
         • Microsoft Authenticator
         • Authy
         • 1Password
         • Any TOTP-compatible app

        Example:
         vastai tfa totp-setup
    """),
)
def tfa__totp_setup(args):
    """Generate a TOTP secret and QR code for setting up Authenticator app 2FA."""
    url = apiurl(args, "/api/v0/tfa/totp-setup/")

    r = http_post(args, url, headers=apiheaders(args), json={})
    r.raise_for_status()

    response_data = r.json()
    if args.raw:
        print(json.dumps(response_data, indent=2))
        return

    # Extract the secret and provisioning URI
    secret = response_data["secret"]
    provisioning_uri = response_data["provisioning_uri"]

    # Display the setup information
    print("\n" + "="*60)
    print("TOTP (Authenticator App) 2FA Setup")
    print("="*60)

    print("\nScan this QR code with your Authenticator app:\n")

    try:  # Generate and display QR code in terminal
        import qrcode
        qr = qrcode.QRCode(border=2)
        qr.add_data(provisioning_uri)
        qr.make()
        qr.print_ascii(tty=True)
    except ImportError:
        print("  [QR code display requires 'qrcode' package]")
        print(f"  Install with: pip install qrcode")
        print(f"\n  Or manually enter this URI in your app:")
        print(f"  {provisioning_uri}")

    print("\nOR Manual Entry Key (type this into your Authenticator app):")
    print(f"  {secret}")

    print("\nNext Steps:")
    print("  1. Your Authenticator app should now display a 6-digit code")
    print("  2. Complete setup by running:")
    print(f"     vastai tfa activate --secret {secret} <CODE>")
    print("\n" + "="*60 + "\n")


@parser.command(
    argument("method_id", metavar="METHOD_ID", help="ID of the 2FA method to update (see `vastai tfa status`)", type=int),
    argument("-l", "--label", help="New label/name for this 2FA method", type=str, default=None),
    argument("-p", "--set-primary", help="Set this method as the primary/default 2FA method", default=None),
    usage="vastai tfa update METHOD_ID [--label LABEL] [--set-primary]",
    help="Update a 2FA method's settings",
    epilog=deindent("""
        Update the label or primary status of a 2FA method.

        The label is a friendly name to help you identify different methods
        (e.g. "Work Phone", "Personal Authenticator").

        The primary method is your preferred/default 2FA method.

        Examples:
         vastai tfa update 123 --label "Work Phone"
         vastai tfa update 456 --set-primary
         vastai tfa update 789 --label "Backup Authenticator" --set-primary
    """),
)
def tfa__update(args):
    """Update settings for an existing 2FA method."""
    url = apiurl(args, "/api/v0/tfa/update/")

    # Build payload with only provided fields
    payload = {
        "tfa_method_id": args.method_id
    }

    if args.label is not None:
        payload["label"] = args.label

    if args.set_primary is not None:
        if args.set_primary.lower() in {'true', 't'}:
            args.set_primary = True
        elif args.set_primary.lower() in {'false', 'f'}:
            args.set_primary = False
        else:
            print("Error: --set-primary must be <t|true> or <f|false>")
            return

        payload["is_primary"] = args.set_primary

    # Validate that at least one update field was provided
    if len(payload) == 1:  # only method_id
        print("Error: You must specify at least one field to update (--label or --set-primary)")
        return 1

    r = http_put(args, url, headers=apiheaders(args), json=payload)
    r.raise_for_status()

    response_data = r.json()
    if args.raw:
        print(json.dumps(response_data, indent=2))
        return

    method_info = response_data.get("method", {})

    print(f"\n{SUCCESS} 2FA method updated successfully!")
    if args.label:
        print(f"   New label: {args.label}")
    if args.set_primary is not None:
        print(f"   Set as primary method = {args.set_primary}")
    if method_info:
        print("\nUpdated 2FA Method:")
        display_tfa_methods([method_info])
