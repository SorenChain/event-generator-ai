# app/utils/alert_system.py
import asyncio
import smtplib
import os
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
import json

from app.utils.log_monitor import LogMonitor


class AlertSystem:
    """Alert system for monitoring critical issues in the prediction market app"""
    
    def __init__(self, 
                 smtp_server: str = None,
                 smtp_port: int = 587,
                 email_user: str = None,
                 email_password: str = None,
                 recipients: List[str] = None):
        
        # Email configuration (from environment variables)
        self.smtp_server = smtp_server or os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', '587'))
        self.email_user = email_user or os.getenv('ALERT_EMAIL_USER')
        self.email_password = email_password or os.getenv('ALERT_EMAIL_PASSWORD')
        self.recipients = recipients or os.getenv('ALERT_RECIPIENTS', '').split(',')
        
        self.log_monitor = LogMonitor()
        
        # Alert thresholds
        self.thresholds = {
            'max_hours_without_execution': 26,  # Alert if no execution in 26 hours
            'max_critical_errors': 5,           # Alert if more than 5 critical errors
            'max_error_rate': 0.3,              # Alert if error rate > 30%
            'min_successful_events': 1          # Alert if no successful events processed
        }
    
    async def check_cron_job_execution(self) -> Dict:
        """Check if cron job has executed recently"""
        health = await self.log_monitor.check_cron_job_health(
            expected_interval_hours=self.thresholds['max_hours_without_execution']
        )
        
        return {
            'type': 'cron_execution',
            'status': health['status'],
            'critical': health['status'] == 'ERROR',
            'message': health['message'],
            'last_execution': health.get('last_execution')
        }
    
    async def check_critical_errors(self, hours: int = 24) -> Dict:
        """Check for critical errors"""
        collection = await self.log_monitor.get_collection()
        
        critical_count = await collection.count_documents({
            "timestamp": {"$gte": datetime.now() - timedelta(hours=hours)},
            "level": "CRITICAL"
        })
        
        is_critical = critical_count > self.thresholds['max_critical_errors']
        
        # Get latest critical errors
        latest_critical = []
        if critical_count > 0:
            cursor = collection.find({
                "timestamp": {"$gte": datetime.now() - timedelta(hours=hours)},
                "level": "CRITICAL"
            }).sort("timestamp", -1).limit(3)
            
            latest_critical = await cursor.to_list(length=3)
        
        return {
            'type': 'critical_errors',
            'status': 'CRITICAL' if is_critical else 'OK',
            'critical': is_critical,
            'message': f"Found {critical_count} critical errors in last {hours} hours",
            'count': critical_count,
            'threshold': self.thresholds['max_critical_errors'],
            'latest_errors': latest_critical
        }
    
    async def check_error_rate(self, hours: int = 24) -> Dict:
        """Check overall error rate"""
        collection = await self.log_monitor.get_collection()
        
        total_logs = await collection.count_documents({
            "timestamp": {"$gte": datetime.now() - timedelta(hours=hours)}
        })
        
        error_logs = await collection.count_documents({
            "timestamp": {"$gte": datetime.now() - timedelta(hours=hours)},
            "level": {"$in": ["ERROR", "CRITICAL"]}
        })
        
        error_rate = error_logs / total_logs if total_logs > 0 else 0
        is_critical = error_rate > self.thresholds['max_error_rate']
        
        return {
            'type': 'error_rate',
            'status': 'CRITICAL' if is_critical else 'OK',
            'critical': is_critical,
            'message': f"Error rate: {error_rate:.2%} ({error_logs}/{total_logs})",
            'error_rate': error_rate,
            'threshold': self.thresholds['max_error_rate'],
            'error_count': error_logs,
            'total_logs': total_logs
        }
    
    async def check_successful_processing(self, hours: int = 24) -> Dict:
        """Check if events are being processed successfully"""
        collection = await self.log_monitor.get_collection()
        
        successful_events = await collection.count_documents({
            "timestamp": {"$gte": datetime.now() - timedelta(hours=hours)},
            "message": {"$regex": ".*saved successfully.*", "$options": "i"}
        })
        
        is_critical = successful_events < self.thresholds['min_successful_events']
        
        return {
            'type': 'successful_processing',
            'status': 'CRITICAL' if is_critical else 'OK',
            'critical': is_critical,
            'message': f"Successfully processed {successful_events} events in last {hours} hours",
            'successful_count': successful_events,
            'threshold': self.thresholds['min_successful_events']
        }
    
    async def check_stuck_functions(self, hours: int = 24) -> Dict:
        """Check for functions that started but never completed"""
        collection = await self.log_monitor.get_collection()
        
        # Find function starts
        started_functions = {}
        cursor = collection.find({
            "timestamp": {"$gte": datetime.now() - timedelta(hours=hours)},
            "extra_data.function_start": "True"
        })
        
        async for log in cursor:
            key = f"{log['function']}_{log['timestamp'].isoformat()}"
            started_functions[key] = log
        
        # Find function completions
        completed_functions = set()
        cursor = collection.find({
            "timestamp": {"$gte": datetime.now() - timedelta(hours=hours)},
            "extra_data.function_complete": "True"
        })
        
        async for log in cursor:
            # Find matching start (within reasonable time window)
            for key, start_log in started_functions.items():
                if (start_log['function'] == log['function'] and 
                    abs((log['timestamp'] - start_log['timestamp']).total_seconds()) < 3600):  # 1 hour max
                    completed_functions.add(key)
                    break
        
        stuck_functions = [
            started_functions[key] for key in started_functions 
            if key not in completed_functions and 
            (datetime.now() - started_functions[key]['timestamp']).total_seconds() > 1800  # 30 minutes
        ]
        
        is_critical = len(stuck_functions) > 0
        
        return {
            'type': 'stuck_functions',
            'status': 'CRITICAL' if is_critical else 'OK',
            'critical': is_critical,
            'message': f"Found {len(stuck_functions)} potentially stuck functions",
            'stuck_functions': stuck_functions
        }
    
    async def run_all_checks(self) -> List[Dict]:
        """Run all health checks"""
        checks = [
            await self.check_cron_job_execution(),
            await self.check_critical_errors(),
            await self.check_error_rate(),
            await self.check_successful_processing(),
            await self.check_stuck_functions()
        ]
        
        return checks
    
    def format_alert_email(self, checks: List[Dict]) -> str:
        """Format checks into an email alert"""
        critical_checks = [check for check in checks if check['critical']]
        
        if not critical_checks:
            return None  # No alert needed
        
        html = f"""
        <html>
        <body>
        <h2>🚨 Prediction Market Alert - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</h2>
        
        <p><strong>{len(critical_checks)} critical issue(s) detected:</strong></p>
        
        <ul>
        """
        
        for check in critical_checks:
            html += f"<li><strong>{check['type'].replace('_', ' ').title()}:</strong> {check['message']}</li>"
        
        html += "</ul><h3>Detailed Information:</h3>"
        
        for check in critical_checks:
            html += f"<h4>{check['type'].replace('_', ' ').title()}</h4>"
            html += f"<p><strong>Status:</strong> {check['status']}</p>"
            html += f"<p><strong>Message:</strong> {check['message']}</p>"
            
            if check['type'] == 'critical_errors' and check.get('latest_errors'):
                html += "<p><strong>Latest Critical Errors:</strong></p><ul>"
                for error in check['latest_errors']:
                    html += f"<li>[{error['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}] {error['function']}: {error['message']}</li>"
                html += "</ul>"
            
            if check['type'] == 'stuck_functions' and check.get('stuck_functions'):
                html += "<p><strong>Stuck Functions:</strong></p><ul>"
                for func in check['stuck_functions']:
                    duration = (datetime.now() - func['timestamp']).total_seconds() / 60
                    html += f"<li>{func['function']} - stuck for {duration:.1f} minutes</li>"
                html += "</ul>"
        
        html += """
        <h3>Next Steps:</h3>
        <ol>
        <li>Check server status and resources</li>
        <li>Review detailed logs in MongoDB collection 'prediction_market_logs'</li>
        <li>Consider restarting the application if issues persist</li>
        </ol>
        
        <p><em>This alert was generated automatically by the Prediction Market monitoring system.</em></p>
        </body>
        </html>
        """
        
        return html
    
    async def send_email_alert(self, checks: List[Dict]) -> bool:
        """Send email alert if critical issues found"""
        if not self.email_user or not self.email_password or not self.recipients:
            print("Email configuration not set. Cannot send alerts.")
            return False
        
        email_content = self.format_alert_email(checks)
        if not email_content:
            print("No critical issues found. No alert sent.")
            return True
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🚨 Prediction Market Alert - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            msg['From'] = self.email_user
            msg['To'] = ', '.join(self.recipients)
            
            # Create HTML part
            html_part = MIMEText(email_content, 'html')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.sendmail(self.email_user, self.recipients, msg.as_string())
            
            print(f"Alert email sent to {len(self.recipients)} recipients")
            return True
            
        except Exception as e:
            print(f"Failed to send email alert: {e}")
            return False
    
    async def run_alert_check(self) -> Dict:
        """Run complete alert check and send notifications if needed"""
        print(f"Running alert check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        checks = await self.run_all_checks()
        critical_issues = [check for check in checks if check['critical']]
        
        # Print summary
        print(f"Completed {len(checks)} checks")
        print(f"Found {len(critical_issues)} critical issues")
        
        for check in checks:
            status_icon = "❌" if check['critical'] else "✅"
            print(f"  {status_icon} {check['type']}: {check['status']}")
        
        # Send alert if critical issues found
        if critical_issues:
            email_sent = await self.send_email_alert(checks)
        else:
            email_sent = True  # No email needed
        
        return {
            'timestamp': datetime.now(),
            'total_checks': len(checks),
            'critical_issues': len(critical_issues),
            'email_sent': email_sent,
            'checks': checks
        }


async def main():
    """CLI main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run prediction market alerts")
    parser.add_argument("--email", action="store_true", help="Send email alerts for critical issues")
    parser.add_argument("--print-only", action="store_true", help="Only print results, don't send emails")
    
    args = parser.parse_args()
    
    alert_system = AlertSystem()
    
    if args.print_only:
        # Just run checks and print results
        checks = await alert_system.run_all_checks()
        print("\nAlert Check Results:")
        print("=" * 50)
        for check in checks:
            status = "CRITICAL" if check['critical'] else "OK"
            print(f"{check['type']:20} {status:10} {check['message']}")
    else:
        # Run full alert check with email
        result = await alert_system.run_alert_check()
        print(f"\nAlert check completed. Email sent: {result['email_sent']}")


if __name__ == "__main__":
    asyncio.run(main())