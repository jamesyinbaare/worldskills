"""WeasyPrint HTML → PDF for guardian consent forms."""

from __future__ import annotations

from datetime import date
from html import escape

from weasyprint import HTML


def _e(value: object | None) -> str:
    if value is None:
        return "—"
    text = str(value).strip()
    return escape(text) if text else "—"


def render_consent_form_pdf(
    *,
    competition_name: str,
    competitor_ref: str,
    given_names: str | None,
    family_name: str | None,
    date_of_birth: date | None,
    guardian_name: str | None = None,
    guardian_email: str | None = None,
    guardian_phone: str | None = None,
) -> bytes:
    display_name = " ".join(
        part for part in [given_names or "", family_name or ""] if part.strip()
    ).strip() or competitor_ref
    dob = date_of_birth.isoformat() if date_of_birth else None

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Guardian consent — {_e(competition_name)}</title>
  <style>
    @page {{ size: A4; margin: 18mm 16mm; }}
    body {{
      font-family: "DejaVu Sans", "Helvetica", "Arial", sans-serif;
      color: #1c2526;
      font-size: 11pt;
      line-height: 1.45;
    }}
    .banner {{
      background: linear-gradient(90deg, #003764 0%, #00853f 100%);
      color: #fff;
      padding: 18px 20px;
      border-radius: 10px;
      margin-bottom: 22px;
    }}
    .banner h1 {{
      margin: 0 0 4px;
      font-size: 18pt;
      letter-spacing: 0.02em;
    }}
    .banner p {{ margin: 0; opacity: 0.92; font-size: 10pt; }}
    h2 {{
      color: #003764;
      font-size: 12pt;
      margin: 22px 0 10px;
      border-bottom: 2px solid #ffcc00;
      padding-bottom: 4px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 8px;
    }}
    th, td {{
      text-align: left;
      vertical-align: top;
      padding: 7px 8px;
      border: 1px solid #d6dce0;
    }}
    th {{
      width: 34%;
      background: #eef3f7;
      color: #003764;
      font-weight: 600;
    }}
    .scopes {{
      list-style: none;
      padding: 0;
      margin: 0;
    }}
    .scopes li {{
      margin: 10px 0;
      padding: 10px 12px;
      border: 1px solid #d6dce0;
      border-radius: 8px;
    }}
    .box {{
      display: inline-block;
      width: 14px;
      height: 14px;
      border: 1.5px solid #003764;
      margin-right: 8px;
      vertical-align: -2px;
    }}
    .sig {{
      margin-top: 18px;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }}
    .sig .line {{
      border-bottom: 1px solid #1c2526;
      height: 36px;
      margin-top: 28px;
    }}
    .note {{
      margin-top: 20px;
      font-size: 9pt;
      color: #4a5557;
    }}
    .gold {{ color: #ffcc00; }}
  </style>
</head>
<body>
  <div class="banner">
    <h1>WorldSkills Ghana — Guardian Consent</h1>
    <p>{_e(competition_name)}</p>
  </div>

  <p>
    A parent or legal guardian must sign this form. Return the signed PDF for
    upload in the competitor portal.
  </p>

  <h2>Competitor</h2>
  <table>
    <tr><th>Full name</th><td>{_e(display_name)}</td></tr>
    <tr><th>Competitor reference</th><td>{_e(competitor_ref)}</td></tr>
    <tr><th>Date of birth</th><td>{_e(dob)}</td></tr>
  </table>

  <h2>Guardian</h2>
  <table>
    <tr><th>Guardian name</th><td>{_e(guardian_name)}</td></tr>
    <tr><th>Guardian email</th><td>{_e(guardian_email)}</td></tr>
    <tr><th>Guardian phone</th><td>{_e(guardian_phone)}</td></tr>
  </table>

  <h2>Consent scopes</h2>
  <p>Tick the scopes you agree to:</p>
  <ul class="scopes">
    <li>
      <span class="box"></span>
      <strong>Participation</strong> — I consent to this competitor taking part
      in the competition named above under WorldSkills Ghana / CTVET rules.
    </li>
    <li>
      <span class="box"></span>
      <strong>Public display</strong> — I also consent to limited public profile
      display (name / photo / results as configured). Optional; participation
      consent is still required.
    </li>
  </ul>

  <div class="sig">
    <div>
      <strong>Guardian signature</strong>
      <div class="line"></div>
    </div>
    <div>
      <strong>Date</strong>
      <div class="line"></div>
    </div>
  </div>

  <p class="note">
    Upload the signed PDF in the competitor portal. Participation consent is
    required before the competitor can progress past review.
  </p>
</body>
</html>
"""
    return HTML(string=html, base_url=".").write_pdf()
