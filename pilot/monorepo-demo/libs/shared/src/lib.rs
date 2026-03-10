//! Shared library for OpenClaw monorepo
//!
//! This library contains common utilities used across the monorepo.

use serde::{Deserialize, Serialize};

/// Configuration structure for services
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ServiceConfig {
    /// Service name
    pub name: String,
    /// Service version
    pub version: String,
    /// Service port
    pub port: u16,
    /// Debug mode flag
    pub debug: bool,
}

impl ServiceConfig {
    /// Create a new service configuration
    ///
    /// # Arguments
    /// * `name` - Service name
    /// * `version` - Service version (semver)
    /// * `port` - Port number to listen on
    pub fn new(name: &str, version: &str, port: u16) -> Self {
        Self {
            name: name.to_string(),
            version: version.to_string(),
            port,
            debug: false,
        }
    }

    /// Enable debug mode
    pub fn with_debug(mut self) -> Self {
        self.debug = true;
        self
    }

    /// Serialize config to JSON
    pub fn to_json(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string_pretty(self)
    }
}

impl Default for ServiceConfig {
    fn default() -> Self {
        Self {
            name: "unknown".to_string(),
            version: "0.0.0".to_string(),
            port: 8080,
            debug: false,
        }
    }
}

/// Validate a service name
///
/// # Arguments
/// * `name` - Service name to validate
///
/// # Returns
/// * `true` if name is valid
pub fn validate_service_name(name: &str) -> bool {
    if name.is_empty() || name.len() > 50 {
        return false;
    }
    name.chars().all(|c| c.is_alphanumeric() || c == '-' || c == '_')
}

/// Calculate health score based on metrics
///
/// # Arguments
/// * `uptime_seconds` - Service uptime in seconds
/// * `error_rate` - Error rate (0.0 to 1.0)
///
/// # Returns
/// Health score from 0 to 100
pub fn calculate_health_score(uptime_seconds: u64, error_rate: f64) -> u8 {
    let uptime_score = (uptime_seconds.min(3600) as f64 / 3600.0 * 50.0) as u8;
    let error_score = ((1.0 - error_rate.min(1.0)) * 50.0) as u8;
    uptime_score.min(50) + error_score.min(50)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_service_config_new() {
        let config = ServiceConfig::new("test-service", "1.0.0", 8080);
        assert_eq!(config.name, "test-service");
        assert_eq!(config.version, "1.0.0");
        assert_eq!(config.port, 8080);
        assert!(!config.debug);
    }

    #[test]
    fn test_service_config_with_debug() {
        let config = ServiceConfig::new("test", "1.0.0", 8080).with_debug();
        assert!(config.debug);
    }

    #[test]
    fn test_service_config_default() {
        let config = ServiceConfig::default();
        assert_eq!(config.name, "unknown");
        assert_eq!(config.version, "0.0.0");
        assert_eq!(config.port, 8080);
    }

    #[test]
    fn test_service_config_to_json() {
        let config = ServiceConfig::new("test", "1.0.0", 8080);
        let json = config.to_json();
        assert!(json.is_ok());
        let json_str = json.unwrap();
        assert!(json_str.contains("test"));
        assert!(json_str.contains("1.0.0"));
    }

    #[test]
    fn test_validate_service_name() {
        assert!(validate_service_name("valid-name"));
        assert!(validate_service_name("valid_name"));
        assert!(validate_service_name("ValidName123"));
        assert!(!validate_service_name(""));
        assert!(!validate_service_name("invalid name with spaces"));
        assert!(!validate_service_name("a".repeat(51).as_str()));
    }

    #[test]
    fn test_calculate_health_score() {
        // Perfect health
        assert_eq!(calculate_health_score(3600, 0.0), 100);
        
        // New service with some errors
        assert!(calculate_health_score(0, 0.1) < 50);
        
        // Old service with high error rate
        assert!(calculate_health_score(7200, 0.5) < 75);
        
        // Maximum uptime bonus
        assert_eq!(calculate_health_score(3600, 0.0), 100);
    }

    #[test]
    fn test_service_config_equality() {
        let config1 = ServiceConfig::new("test", "1.0.0", 8080);
        let config2 = ServiceConfig::new("test", "1.0.0", 8080);
        let config3 = ServiceConfig::new("other", "1.0.0", 8080);
        
        assert_eq!(config1, config2);
        assert_ne!(config1, config3);
    }
}
