#!/usr/bin/env python3
"""
Configuration parser for routing rules in YAML format
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfigParser:
    """Parse YAML routing configuration files"""
    
    def __init__(self, config_file: str):
        self.config_file = Path(config_file)
        
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    def parse(self) -> List[Dict]:
        """Parse configuration file and return routing rules
        
        Returns:
            List of routing rule dictionaries
        """
        try:
            with open(self.config_file, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data:
                logger.warning("Configuration file is empty")
                return []
            
            rules = data.get('routing_rules', [])
            
            # Validate rules
            validated_rules = []
            for rule in rules:
                if self._validate_rule(rule):
                    validated_rules.append(rule)
                else:
                    logger.warning(f"Skipping invalid rule: {rule.get('name', 'unknown')}")
            
            logger.info(f"Loaded {len(validated_rules)} routing rules from {self.config_file}")
            return validated_rules
        
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error in {self.config_file}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error parsing configuration: {e}")
            raise
    
    def _validate_rule(self, rule: Dict) -> bool:
        """Validate a routing rule
        
        Required fields:
        - name: Rule name
        - target_device: Target device name
        
        At least one of:
        - applications: List of application names
        - application_keywords: List of keywords to match
        """
        required_fields = ['name', 'target_device']
        
        for field in required_fields:
            if field not in rule:
                logger.warning(f"Rule missing required field: {field}")
                return False
        
        has_app_matcher = (
            'applications' in rule or
            'application_keywords' in rule
        )
        
        if not has_app_matcher:
            logger.warning(f"Rule '{rule['name']}' has no application matchers")
            return False
        
        return True
    
    @staticmethod
    def create_template(output_file: str):
        """Create a template configuration file"""
        template = {
            'routing_rules': [
                {
                    'name': 'Example Gaming Rule',
                    'applications': ['steam', 'lutris', 'games'],
                    'target_device': 'alsa_card.pci-0000_00_1f.3-platform-skl_hda_dsp_generic',
                    'enable_default_fallback': True
                },
                {
                    'name': 'Example Video Call Rule',
                    'applications': ['firefox', 'chrome'],
                    'application_keywords': ['meet', 'teams', 'zoom'],
                    'target_device': 'alsa_card.usb-0000_00_00.0',
                    'enable_default_fallback': False
                }
            ]
        }
        
        try:
            with open(output_file, 'w') as f:
                yaml.dump(template, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Template configuration created: {output_file}")
        except Exception as e:
            logger.error(f"Failed to create template: {e}")
            raise
