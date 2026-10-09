# Telegram Bot
An asynchronous Telegram bot built with Python that automates the process of monitoring and booking work shifts on a corporate scheduling portal. 

## Features
* **Automated Booking:** Uses Selenium WebDriver (Headless Chrome) to navigate the portal and book shifts.
* **Conflict Resolution:** Automatically calculates the mandatory 10-hour rest period between shifts. If a blocking shift is found, the bot can forcefully cancel it and book the new target shift.
* **Multi-user Support:** SQLite database integration allows multiple users to register via Telegram and manage their independent shift requests.
* **FSM Interfaces:** Clean and intuitive Telegram UI using `aiogram` Finite State Machines and Inline Keyboards.

## Tech Stack
* **Python 3.10+**
* **aiogram 3.x** (Async Telegram Bot API)
* **Selenium** (Web Scraping & Browser Automation)
* **SQLite** (Relational Database)
