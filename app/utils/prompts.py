"""
Prompt template utilities for the prediction market app.
"""

class PromptTemplate:
    """Simple prompt template class to mimic LangChain's PromptTemplate."""
    
    def __init__(self, template):
        """
        Initialize a prompt template.
        
        Args:
            template: String template with {placeholders}
        """
        self.template = template
        
    def format(self, **kwargs):
        """
        Format the template with provided values.
        
        Args:
            **kwargs: Key-value pairs to replace placeholders
            
        Returns:
            Formatted string
        """
        return self.template.format(**kwargs)