# HMH Group — Construction Payroll System
## System Proposal & Feature Specification

---

## 1. Overview

The HMH Payroll System is a purpose-built payroll and attendance management solution designed specifically for HMH Group's permanent construction staff. The system integrates directly into the existing HMH procurement and project management platform, giving management a single place to run the business — from purchase orders and deliveries through to staff wages and compliance.

The system is designed for South African labour law and tax compliance and handles all statutory obligations automatically, including PAYE, UIF, and SDL calculations and reporting.

---

## 2. Who The System Is For

The payroll system covers **HMH Group's permanent employed staff only**. Subcontractors, labour-only suppliers, and third-party contractors are excluded and continue to be managed through the procurement module as supplier payments.

---

## 3. Core System Features

### 3.1 Employee Management
- Full employee profile: name, ID number, job title/trade, employment start date, bank account details
- Employment type: permanent salaried or daily-rate wage worker
- Site/project assignment per employee
- Emergency contact details
- Document storage: employment contract, ID copy, bank confirmation letter
- Employee status management: active, suspended, terminated

### 3.2 Attendance & Time Tracking
- Daily clock-in and clock-out per employee
- Attendance linked to specific site and project
- Automatic calculation of hours worked and days worked per pay period
- Half-day and late arrival tracking
- Absence recording with reason codes: sick leave, annual leave, unpaid absence, family responsibility leave
- Leave balances tracked automatically per employee
- Overtime recording and calculation

### 3.3 Payroll Calculation Engine
- Support for both **monthly salaried** and **daily-rate** workers
- Automatic gross pay calculation based on days/hours worked from attendance records
- Overtime calculations (1.5× for weekdays after 9 hours, 2× for Sundays and public holidays) in line with the Basic Conditions of Employment Act
- Advance/loan deductions tracked and deducted automatically over agreed periods
- Tool or uniform deductions where applicable
- Full audit trail of every calculation for every pay run

### 3.4 Pay Runs
- Weekly, fortnightly, or monthly pay cycles (configurable per employee group)
- Pay run preview before finalising — manager reviews and approves before any payments are processed
- Pay run history: every pay run is permanently recorded and cannot be altered after approval
- Ability to process corrections in the following pay run (no backdating)

### 3.5 Payslips
- Automatically generated payslip for every employee every pay run
- Shows gross earnings, all deductions (PAYE, UIF, union fees, advances), and net pay
- Payslips can be printed or sent via WhatsApp/email directly from the system
- Payslip format complies with South African labour law requirements

### 3.6 Reporting & Exports
- Monthly payroll summary report per project/site
- Individual employee earnings history
- EMP201 report pre-populated for submission to SARS
- UIF contribution report for monthly submission
- SDL levy report
- Year-end IRP5/IT3(a) certificate preparation (employee tax certificates)
- Export to CSV and PDF

---

## 4. Statutory Obligations & Tax Compliance

### 4.1 PAYE — Pay-As-You-Earn

PAYE is a mandatory deduction from each employee's salary on behalf of SARS. The system calculates PAYE automatically each month using the current SARS tax tables, which are updated in the system every year when SARS publishes the new budget.

**How it works in the system:**
- Each employee's monthly taxable income is calculated (gross salary minus allowable deductions)
- SARS tax tables are applied to determine the monthly PAYE amount
- Primary, secondary, and tertiary rebates are applied automatically based on the employee's age
- The PAYE amount is deducted from the employee's net pay and held for remittance to SARS
- The system generates a pre-populated **EMP201 return** every month, ready for submission to SARS by the **7th of the following month**
- A payment reminder notification is sent to the designated administrator on the 1st of each month

> **Important:** PAYE must be remitted to SARS by the 7th of each month without exception. Late payment results in penalties of 10% of the outstanding amount plus interest at the repo rate + 7%. The system flags any pay runs completed after the 25th of the month as requiring urgent EMP201 submission.

### 4.2 UIF — Unemployment Insurance Fund

UIF provides short-term relief to workers who become unemployed, ill, or take maternity leave.

**Contribution structure:**
| Contributor | Rate | Basis |
|---|---|---|
| Employee | 1% | Gross monthly remuneration (capped at R17,712/month) |
| Employer (HMH Group) | 1% | Gross monthly remuneration (capped at R17,712/month) |
| **Total** | **2%** | |

**How it works in the system:**
- The employee's 1% is automatically deducted from their net pay each month
- The employer's matching 1% is calculated and recorded as a company liability
- Earnings above R17,712 per month are excluded from UIF calculation (legislative cap)
- The system generates a monthly UIF declaration (UI-19) ready for submission to the Department of Employment and Labour
- Both employee and employer contributions are included in the EMP201 return to SARS

### 4.3 SDL — Skills Development Levy

SDL is a levy paid by employers to fund skills development programmes across South Africa through the SETA (Sector Education and Training Authority) relevant to the construction industry (CETA).

**Applicability:**
- SDL applies only if HMH Group's **total annual payroll exceeds R500,000**
- If the annual payroll is below R500,000, SDL is not applicable

**Contribution structure:**
| Contributor | Rate | Basis |
|---|---|---|
| Employer (HMH Group) only | 1% | Total monthly payroll (all employees) |

> Note: SDL is an **employer-only** cost. It is NOT deducted from employee wages.

**How it works in the system:**
- The system tracks the cumulative annual payroll automatically
- Once the R500,000 threshold is reached, SDL is calculated at 1% of the monthly payroll going forward
- SDL is included in the monthly EMP201 return and must be paid to SARS by the **7th of the following month** alongside PAYE and UIF
- The system shows a running total of SDL contributions for the financial year

### 4.4 Union Fees

Employees who are members of a registered trade union (for example BCAWU — Building, Construction and Allied Workers Union, or NUM — National Union of Mineworkers) have their union membership fees deducted from their pay and remitted to their union monthly.

**How it works in the system:**
- Each employee's union membership is recorded on their profile (union name, membership number, monthly fee amount)
- Union fees are deducted from net pay automatically each pay run
- A union remittance report is generated monthly per union showing all members and the total amount to be paid over
- Union fees do not affect PAYE calculations (they are not a pre-tax deduction)
- Multiple unions can be configured if staff belong to different unions

---

## 5. Attendance Verification Options

The system requires each employee to clock in and clock out at the start and end of every shift. Three options are available depending on the hardware the company chooses to invest in.

---

### Option A — USB Fingerprint Scanner

A fingerprint scanner device is connected to the site tablet via a USB-OTG (On-The-Go) cable. Each worker registers their fingerprint once during onboarding. From then on, they scan their finger to clock in and out — no photos, no PINs, no cards.

**How it works:**
1. Worker places finger on scanner
2. System matches against their enrolled fingerprint
3. Clock-in/out recorded in under 3 seconds

**Recommended hardware:**

| Device | Price (incl. VAT) | Notes |
|---|---|---|
| SecuGen Hamster Pro 20 | R1,200 — R1,600 | Industry standard, good read rate |
| Futronic FS80 | R900 — R1,300 | Budget option, reliable in clean conditions |
| DigitalPersona 4500 | R1,400 — R1,900 | Higher accuracy, better for worn fingerprints |
| USB-OTG Adapter | R80 — R150 | Required to connect scanner to tablet |

**One-time hardware cost: approximately R1,000 — R2,000**
**Ongoing monthly cost: R0**

**Pros:**
- No ongoing costs after hardware purchase
- Fast and familiar to workers
- Works offline (no internet needed for the scan itself)
- Cannot be spoofed by a photo

**Cons:**
- Construction workers have rough, calloused, and often dirty hands — fingerprint scanners have a higher false rejection rate in these conditions (scanner may not read the finger on first attempt)
- If the scanner is damaged or lost, a replacement must be purchased
- Requires a compatible Android tablet with USB-OTG support

---

### Option B — Camera-Based Face Recognition (AWS Rekognition)

The site tablet's built-in camera is used to verify the worker's identity. When clocking in or out, the worker looks at the tablet and blinks once. AWS Rekognition confirms it is a live person (not a photo or video) and matches their face against their enrolled photo. No additional hardware is required.

**How it works:**
1. Worker taps their name on the tablet screen
2. Camera opens — worker looks at the camera and blinks once
3. AWS confirms liveness (cannot be spoofed by a photo or a video)
4. Face is matched against their enrolled photo
5. Clock-in/out recorded in under 5 seconds

**Why it cannot be faked:**
The AWS Liveness Detection system uses an active challenge (random blink prompt) combined with depth and texture analysis to confirm a real human face is present. Holding up a printed photo, a phone screen, or playing a video will all fail the liveness check. This is the same technology used by South African banks for facial onboarding.

**Monthly cost for 50 staff (clock-in AND clock-out, 6-day work week):**

| Scenario | Checks/Month | Monthly Cost (USD) | Monthly Cost (ZAR) |
|---|---|---|---|
| Clock-in only, 5-day week | 1,100 | $22 | ~R407 |
| Clock-in + out, 5-day week | 2,200 | $44 | ~R814 |
| Clock-in only, 6-day week | 1,300 | $26 | ~R481 |
| **Clock-in + out, 6-day week** | **2,600** | **$52** | **~R962** |

> **First 12 months free:** AWS provides 10,000 face liveness checks per month at no cost for the first year. For 50 staff clocking in and out over a 6-day week, this covers approximately **3.8 months of checks for free per year.**

**One-time hardware cost: R0** (uses the tablet's built-in camera)
**Ongoing monthly cost: ~R962/month** (worst case, both scans, 6-day week)

**Pros:**
- No additional hardware — works on any tablet with a camera
- Cannot be spoofed by photos, videos, or masks
- Works well regardless of hand condition (dirty hands are not a factor)
- Consistent and fast clock-in experience
- Auto-identifies the worker — no need to tap their name if face is recognised on approach

**Cons:**
- Requires a stable internet connection for each scan
- Ongoing monthly cost
- Bright direct sunlight can affect camera quality (tablet should be placed in shade or indoors at site entrance)

---

### Option C — PIN Entry (No Biometrics)

Each worker is assigned a 4-digit PIN. They enter their PIN on the tablet to clock in and out. No hardware required beyond the tablet itself.

**Monthly cost: R0**

**Pros:**
- Simplest to build and run
- No hardware, no ongoing costs
- Works offline

**Cons:**
- Workers can share PINs and clock each other in ("buddy clocking") — defeats the purpose of attendance tracking
- Not recommended for payroll-linked attendance as it cannot be relied upon for wage calculation accuracy

---

### Attendance Option Comparison

| | USB Fingerprint | Face Recognition | PIN Only |
|---|---|---|---|
| Hardware cost | R1,000 — R2,000 | R0 | R0 |
| Monthly cost | R0 | ~R962 | R0 |
| Spoof-proof | Yes | Yes | No |
| Works offline | Yes | No | Yes |
| Dirty hands issue | Yes | No | No |
| Setup complexity | Medium | Low | Low |
| **Recommended for construction** | Conditional | **Yes** | Not recommended |

---

## 6. System Pricing

| Package | Monthly Cost |
|---|---|
| **Full Payroll System** (PAYE, UIF, SDL, union fees, payslips, EMP201, attendance via PIN or manual sign-off) | **R2,500/month** |
| + Face Recognition Attendance (AWS, clock-in & out, 6-day week, 50 staff) | + ~R962/month |
| + USB Fingerprint Scanner (hardware only, one-time) | + R1,000 — R2,000 once-off |

**Recommended package for HMH Group:**

> **R2,500/month** system base + **~R962/month** AWS face recognition = **approximately R3,462/month all-in**
>
> This gives HMH Group a fully compliant, spoof-proof payroll and attendance system with no hardware to buy, maintain, or replace.

For comparison: manually administering payroll for 50 staff including statutory calculations, payslip printing, and EMP201 submissions takes approximately **2 full working days per month** for an administrator. At an administrator's salary of R15,000/month, that is roughly **R1,500 in labour cost per payroll run** — before accounting for the risk of SARS penalties for calculation errors.

---

## 7. Implementation Timeline

| Phase | Work | Estimated Duration |
|---|---|---|
| Phase 1 | Employee profiles, bank details, rates setup | 1 week |
| Phase 2 | Attendance system (clock-in/out, leave management) | 1 week |
| Phase 3 | Payroll engine (PAYE, UIF, SDL, union fees, payslips) | 1.5 weeks |
| Phase 4 | Face recognition enrollment and clock-in/out | 1 week |
| Phase 5 | EMP201 / UIF reports, testing and go-live | 1 week |
| **Total** | | **~5.5 weeks** |

---

## 8. Important Notes

- **SARS tax tables** are updated annually in February/March after the national budget. The system will be updated to reflect the new tables each year at no additional cost.
- **This system does not replace a registered tax practitioner or HR consultant.** It automates the calculations and reporting, but HMH Group remains responsible for the accuracy of employee information entered and for timely submissions to SARS.
- **Data privacy:** All employee personal information (ID numbers, bank details, biometric data) is stored securely and in accordance with POPIA (Protection of Personal Information Act). Face data used for recognition is processed through AWS and is not stored permanently after matching.
- **Internet requirement:** The base payroll system can run offline for most functions. Face recognition requires an internet connection at the time of scanning. EMP201 submission requires internet.

---

*Document prepared for HMH Group — July 2026*
*HMH Procurement & Project Management System*
