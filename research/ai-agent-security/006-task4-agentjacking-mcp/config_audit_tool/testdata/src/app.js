// Sample JavaScript application config patterns
const apiKey = process.env.API_KEY;
const token = process.env["GITHUB_TOKEN"];

const config = {
  databaseUrl: "postgres://admin:P@ssw0rd@db.example.com:5432/app",
  stripeSecret: "sk_test_51ExampleSecretKeyValue123456",
  sentryDsn: "https://abcdef1234567890abcdef1234567890@o0.ingest.sentry.io/123",
  publicName: "my-app",
};

const MONGO_URI = "mongodb+srv://user:mypassword@cluster0.example.mongodb.net/db";
let webhook_secret = "whsec_abc123def456ghi789jkl012";

module.exports = { config, apiKey, MONGO_URI };