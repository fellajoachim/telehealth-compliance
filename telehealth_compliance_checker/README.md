# Telehealth Compliance Checker - Upgraded

A tool to analyze telehealth websites for HIPAA, FDA, LegitScript, and FTC compliance issues.

## New Features in This Upgrade

- **Context-Aware Branded Medication Analysis**: Differentiates between blog posts and product pages when evaluating branded medication mentions
- **Guarantee Terms Handling**: Allows money-back guarantees that specify weight loss amounts and timeframes
- **Enhanced URL Handling**: Supports URLs without "https://" prefix and improves crawling for sites with protection mechanisms
- **Improved Crawler for Protected Sites**: Special handling for sites like hims.com with anti-scraping measures
- **New Prohibited Terms Detection**: Added detection for terms like "proven", "efficacy", "safe", "semaglutide", "tirzepatide", and "same ingredients"
- **GLP-1 Compliance Reference Materials**: Integrated guidelines from Novo Nordisk and Lilly regarding GLP-1 selling compliance

## Features

- **Comprehensive Analysis**: Crawls telehealth websites to identify compliance issues across all pages
- **Violation Detection**: Identifies problematic content including:
  - Improper use of branded medication names (like Ozempic)
  - Exaggerated or "miracle" claims
  - Unsubstantiated weight loss claims
  - Inappropriate medical advice
  - HIPAA privacy issues
  - Prescription requirement violations
- **Detailed Reporting**: Generates reports with:
  - Overall compliance score (out of 100)
  - Breakdown by regulatory category (HIPAA, FDA, LegitScript, FTC, Technical)
  - Prioritized recommendations for fixing issues
  - Detailed findings with context and location

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/telehealth-compliance-checker.git
cd telehealth-compliance-checker

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Running Locally

```bash
streamlit run telehealth_compliance_checker.py
```

This will start a local Streamlit server and open the app in your web browser.

### Deploying to Streamlit Cloud

1. Fork this repository to your GitHub account
2. Go to [Streamlit Cloud](https://streamlit.io/cloud)
3. Sign in with your GitHub account
4. Click "New app"
5. Select this repository, the main branch, and the `telehealth_compliance_checker.py` file
6. Click "Deploy"

Your app will be deployed and accessible via a public URL.

## How It Works

1. **Web Crawling**: The tool crawls the specified website, collecting page content, forms, and images
2. **Page Type Detection**: Identifies whether pages are blog posts, product pages, or other content types
3. **Compliance Analysis**: Analyzes the collected content for potential compliance issues with context awareness
4. **Scoring**: Calculates compliance scores for different regulatory categories
5. **Recommendations**: Generates prioritized recommendations for improvement

## Compliance Categories

- **HIPAA**: Privacy policies, data security, patient rights
- **FDA**: Medication claims, branded drug references
- **LegitScript**: Prescription requirements, pharmacy partnerships
- **FTC**: Marketing claims, testimonials, truth-in-advertising
- **Technical**: Security, accessibility, required pages

## License

MIT

## Disclaimer

This tool is provided for informational purposes only and does not constitute legal advice. Always consult with qualified legal professionals regarding compliance with healthcare regulations.
