# Node Demo Repository

This is a demo Node.js project for testing the OpenClaw Orchestration Stack's Node/TypeScript support.

## Structure

```
.
├── src/
│   └── index.js          # Main calculator module
├── tests/
│   └── calculator.test.js  # Test suite
├── .openclaw/
│   └── review.yaml       # OpenClaw configuration
├── package.json          # Node.js project config
└── README.md            # This file
```

## Usage

```bash
# Install dependencies
npm install

# Run tests
npm test

# Run linting
npm run lint

# Start the application
npm start
```

## OpenClaw Integration

This project demonstrates:
- Node.js language detection via `package.json`
- Test command execution with `npm test`
- Lint integration with ESLint
- Security scanning with `npm audit`
