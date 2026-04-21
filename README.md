🏗️ HMH Construction Management System

A full-stack construction management platform designed for HMH Group to manage:

Projects & Sites
BOQs (Bill of Quantities)
Procurement & Suppliers
Deliveries & Stock
Fuel Tracking
Payments & Invoices
Site Operations (Mobile PWA)
⚙️ Tech Stack
Backend
FastAPI (Python)
PostgreSQL (Render)
SQLAlchemy ORM
JWT Authentication
Frontend
React + TypeScript
Tailwind CSS
Vite
Hosting
Backend: Render
Database: Render PostgreSQL
Frontend: Vercel (or Netlify)
📁 Project Structure
hmh-system/
│
├── hmh-backend/        # FastAPI backend
├── hmh-frontend/       # React frontend (Office + Site dashboards)
├── hmh-docs/           # Demo docs, proposals, pricing
🚀 Features (Demo Version)
Office Dashboard
Project management
BOQ creation & tracking
Supplier management
Procurement (Purchase Orders)
Delivery tracking (with discrepancies)
Stock & usage tracking
Fuel logging (equipment + vehicles)
Payments & invoices
Alerts system
Site Dashboard (Mobile PWA)
Optimized for phones
View deliveries
Record material usage
Upload images (proof of delivery/work)
Track stock levels
Capture real-time site data
🧮 VAT Handling

System supports both:

VAT Inclusive pricing
VAT Exclusive pricing

Each item:

Can toggle VAT mode
Automatically calculates totals correctly
⛽ Fuel Tracking

Tracks:

Equipment fuel usage
Delivery vehicles
Generators

Includes:

Litres used
Cost per litre
Total cost (auto-calculated)
Linked to project/site
🔐 Authentication
Role-based access:
Owner
Office Admin
Office User
Site Manager
Site Staff
First login:
Users must set their own password
Forced redirect to /set-password
📦 File Upload Support

Supports:

Images (site photos, delivery proof)
PDFs (invoices, POs)
Spreadsheets (BOQs)
🧪 Demo Data

Seed script creates:

Projects, sites, lots
BOQs
Suppliers
Purchase orders
Deliveries
Stock usage
Fuel logs
Payments & invoices
▶️ Running Locally
Backend
cd hmh-backend
python -m venv .venv
.venv\Scripts\activate   # Windows

pip install -r requirements.txt
uvicorn main:app --reload
Frontend
cd hmh-frontend
npm install
npm run dev
🌐 Deployment (Demo Setup)
Database: Render PostgreSQL
Backend: Render Web Service
Frontend: Vercel
📊 Demo Goal

This system is built to demonstrate:

Full construction workflow digitization
Real-time site → office data sync
Procurement automation
Cost tracking (materials + fuel)
📌 Status

🚧 Demo Version (V1) Complete
🚀 Production Version Planned
