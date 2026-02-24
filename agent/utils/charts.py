"""
Chart generation utility for Brain
Uses matplotlib to create visual representations of audit data
"""
import io
import matplotlib
matplotlib.use('Agg') # Set non-interactive backend for thread-safety and headless env
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np
import threading
import textwrap

# Global lock for matplotlib pyplot calls (which are not thread-safe)
matplotlib_lock = threading.Lock()

def generate_user_activity_chart(user_stats: dict, title: str = "User Activity (Last 24h)") -> bytes:
    """
    Generate a horizontal bar chart of user activity
    Args:
        user_stats: dict mapping username/uid to stats (with 'count')
    Returns:
        bytes: PNG image data
    """
    if not user_stats:
        return None

    # Prepare data
    labels = []
    counts = []
    
    # Sort by count
    sorted_stats = sorted(user_stats.items(), key=lambda x: x[1]['count'], reverse=True)
    
    # Take top 10 for readability
    for label, stats in sorted_stats[:10]:
        labels.append(label)
        counts.append(stats['count'])
    
    # Reverse for horizontal bar chart (highest at top)
    labels.reverse()
    counts.reverse()

    with matplotlib_lock:
        # Style
        plt.style.use('dark_background')
        
        # Adjust height based on number of items (Min 4, Max 10)
        fig_height = max(4, min(10, len(labels) * 0.8))
        fig, ax = plt.subplots(figsize=(10, fig_height))
        
        # Premium color palette (NivaSound theme)
        colors = plt.cm.cool(np.linspace(0.4, 0.9, len(counts)))
        
        # Adjust bar thickness if few items
        width = 0.6 if len(labels) > 3 else 0.4
        bars = ax.barh(labels, counts, color=colors, height=width, edgecolor='white', linewidth=0.5)
        
        # Add counts at the end of bars
        max_count = max(counts) if counts else 1
        for bar in bars:
            w = bar.get_width()
            ax.text(w + (max_count * 0.02), bar.get_y() + bar.get_height()/2, 
                    f'{int(w)}', va='center', color='white', fontweight='bold', fontsize=12)

        ax.set_title(title, pad=20, fontsize=18, fontweight='bold', color='#00d4ff', family='sans-serif')
        ax.set_xlabel('Number of Actions', labelpad=10, fontsize=12, alpha=0.8)
        
        # Better axis styling
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#444444')
        ax.spines['bottom'].set_color('#444444')
        
        ax.tick_params(axis='both', which='major', labelsize=11, colors='#cccccc')
        ax.grid(axis='x', linestyle='--', alpha=0.2, color='#ffffff')

        plt.tight_layout()

        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        
        return buf.getvalue()

def generate_action_distribution_pill(action_stats: dict, title: str = "Action Distribution") -> bytes:
    """
    Generate a pie chart of action types
    """
    if not action_stats:
        return None
        
    labels = list(action_stats.keys())
    sizes = list(action_stats.values())
    
    with matplotlib_lock:
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(8, 8))
        
        # Professional color palette
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        
        wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct='%1.1f%%', 
                                        startangle=140, colors=colors[:len(labels)],
                                        pctdistance=0.85, explode=[0.05]*len(labels))
        
        # Draw circle for donut chart
        centre_circle = plt.Circle((0,0), 0.70, fc='#121212') # Match dark background
        fig.gca().add_artist(centre_circle)
        
        ax.set_title(title, pad=20, fontsize=16, fontweight='bold', color='#00d4ff')
        ax.axis('equal') 
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        
        return buf.getvalue()

def generate_professional_dashboard(user_stats: dict, action_stats: dict, security_stats: dict, hourly_stats: dict = None, role_stats: dict = None) -> bytes:
    """
    Generate a professional 2x2 multi-plot dashboard
    Args:
        user_stats: dict of top users
        action_stats: dict of category distribution
        security_stats: dict with 'success' and 'fail' counts
        hourly_stats: dict mapping hour (0-23) to count
        role_stats: dict mapping role names to count
    """
    from matplotlib.ticker import MaxNLocator
    
    with matplotlib_lock:
        plt.style.use('dark_background')
        fig = plt.figure(figsize=(16, 14))
        fig.patch.set_facecolor('#0f172a') # Deep navy background
        
        # 1. Action Distribution (Donut) - Top Left (0,0)
        ax1 = plt.subplot2grid((2, 2), (0, 0))
        if action_stats:
            labels = list(action_stats.keys())
            sizes = list(action_stats.values())
            colors = ['#38bdf8', '#818cf8', '#c084fc', '#fb7185', '#fbbf24']
            
            wedges, texts, autotexts = ax1.pie(sizes, labels=labels, autopct='%1.0f%%', 
                                            startangle=140, colors=colors[:len(labels)],
                                            pctdistance=0.75, wedgeprops=dict(width=0.4))
            plt.setp(autotexts, size=10, weight="bold", color="white")
            plt.setp(texts, size=11, color="#cbd5e1")
            ax1.set_title("ACTIVITY REGIONS", pad=20, fontsize=14, fontweight='bold', color='#38bdf8')

        # 2. Security Health (Vertical Bar) - Top Right (0,1)
        ax2 = plt.subplot2grid((2, 2), (0, 1))
        if security_stats:
            categories = ['Success', 'Failure']
            vals = [security_stats.get('success', 0), security_stats.get('fail', 0)]
            ax2.bar(categories, vals, color=['#10b981', '#ef4444'], alpha=0.8, width=0.4)
            ax2.set_title("SECURITY PERFORMANCE", pad=20, fontsize=14, fontweight='bold', color='#10b981')
            ax2.spines['top'].set_visible(False)
            ax2.spines['right'].set_visible(False)
            ax2.grid(axis='y', linestyle='--', alpha=0.1)
            ax2.yaxis.set_major_locator(MaxNLocator(integer=True))
            for i, v in enumerate(vals):
                ax2.text(i, v + (max(vals or [1]) * 0.02), str(int(v)), ha='center', fontweight='bold', color='white')

        # 3. Role Engagement (Vertical Bar) - Bottom Left (1,0)
        ax3 = plt.subplot2grid((2, 2), (1, 0))
        if role_stats:
            # Standard roles order
            roles = ["SUPERADMIN", "ADMIN", "STAFF", "ARTIST", "USER"]
            counts = [role_stats.get(r, 0) for r in roles]
            
            # Filter out labels for cleaner look
            colors = ['#f43f5e', '#ec4899', '#8b5cf6', '#3b82f6', '#10b981'] # Distinct role colors
            bars = ax3.bar(roles, counts, color=colors, width=0.3, alpha=0.9) # Narrow width=0.3
            
            ax3.set_title("ROLE ENGAGEMENT", pad=20, fontsize=14, fontweight='bold', color='#c084fc')
            ax3.spines['top'].set_visible(False)
            ax3.spines['right'].set_visible(False)
            ax3.grid(axis='y', linestyle='--', alpha=0.1)
            ax3.yaxis.set_major_locator(MaxNLocator(integer=True))
            
            # Rotate labels if too long
            plt.setp(ax3.get_xticklabels(), rotation=15, ha="right", size=9, color="#94a3b8")
            
            for bar in bars:
                h = bar.get_height()
                ax3.text(bar.get_x() + bar.get_width()/2, h + (max(counts or [1]) * 0.02), 
                        str(int(h)), ha='center', color='white', fontweight='bold', size=10)

        # 4. Hourly Activity Trend (Line/Area) - Bottom Right (1,1)
        ax4 = plt.subplot2grid((2, 2), (1, 1))
        if hourly_stats:
            # Sort hours chronologically (past 24h)
            hours = sorted(hourly_stats.keys())
            volumes = [hourly_stats[h] for h in hours]
            
            # Plot with gradient fill
            ax4.plot(hours, volumes, color='#fbbf24', linewidth=3, marker='o', markersize=4)
            ax4.fill_between(hours, volumes, color='#fbbf24', alpha=0.1)
            
            ax4.set_title("HOURLY ACTIVITY TREND", pad=20, fontsize=14, fontweight='bold', color='#fbbf24')
            ax4.set_xlabel("Hour (24h)", fontsize=10, color='#94a3b8')
            ax4.spines['top'].set_visible(False)
            ax4.spines['right'].set_visible(False)
            ax4.grid(axis='y', linestyle='--', alpha=0.1)
            ax4.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax4.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))

        plt.suptitle("NIVASOUND INTELLIGENCE OPS DASHBOARD", fontsize=20, fontweight='bold', color='#00d4ff', y=0.98)
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

def render_table_to_image(data: list[list], headers: list[str], title: str = "NivaSound Data Report") -> bytes:
    """
    Render a professional table as a PNG image using matplotlib
    Args:
        data: List of rows (lists)
        headers: List of column names
        title: Title of the table
    Returns:
        bytes: PNG image data
    """
    if not data:
        return None

    with matplotlib_lock:
        plt.style.use('dark_background')
        
        num_rows = len(data)
        num_cols = len(headers)
        
        # NGO: Define font sizes for the table
        base_font_size = 11
        header_font_size = 12

        # 1. Proportional wrapping based on content characteristics (purely heuristic)
        wrapped_data = []
        for row in data:
            wrapped_row = []
            for i, cell in enumerate(row):
                val = str(cell)
                
                # HEURISTIC: Detect "Token" columns (IDs/Slugs) vs "Narrative" columns (Descriptions/Titles)
                # Tokens have low space density; Narratives have high space density.
                space_density = val.count(" ") / len(val) if len(val) > 10 else 0
                
                # IDs/Slugs (Tokens) should avoid wrapping. Narratives can wrap more generously.
                wrap_limit = 50 if space_density > 0.08 else (42 if space_density == 0 else 32)
                
                if len(val) > wrap_limit:
                    val = textwrap.fill(val, width=wrap_limit)
                wrapped_row.append(val)
            wrapped_data.append(wrapped_row)
        
        # 2. Calculate column widths using a density-invariant system
        col_max_chars = []
        for i in range(num_cols):
            max_len = len(str(headers[i]))
            for row in wrapped_data:
                max_line_len = max([len(line) for line in row[i].split('\n')]) if i < len(row) else 0
                max_len = max(max_len, max_line_len)
            col_max_chars.append(max_len)
            
        weights = []
        for i, length in enumerate(col_max_chars):
            # Evaluate "Narrative Density" for the entire column
            col_sample = [row[i] for row in wrapped_data[:10]]
            avg_space_density = sum(s.count(" ") / len(s) if len(s) > 5 else 0 for s in col_sample) / len(col_sample)
            
            import math
            # Adaptive weighting: Linear for short, Logarithmic for long
            if length < 15:
                base_w = length * 0.12
            else:
                base_w = 1.8 + math.log10(length / 15.0) * 2.2
            
            # Narrative (text/titles) gets a small boost to prevent horizontal squeeze
            if avg_space_density > 0.05:
                base_w *= 1.25
            
            w = max(1.0, min(6.0, base_w))
            weights.append(w)
                
        total_weight = sum(weights)
        norm_widths = [w / total_weight for w in weights]
            
        # 3. Calculate row-wise heights
        row_line_counts = [2.2] # Header height
        for row in wrapped_data:
            m_lines = 1
            for cell in row:
                m_lines = max(m_lines, cell.count('\n') + 1)
            row_line_counts.append(m_lines + 0.4) 
            
        total_content_lines = sum(row_line_counts)
        
        # 4. Calculate dimensions (Dynamic sizing)
        # Tighter width calculation: content-driven
        # NGO: Reducing multiplier to 2.8 for a more compact fit
        fig_width = max(10, min(36, total_weight * 2.8)) 
        fig_height = max(8, total_content_lines * 0.4 + 2) 
        
        # Aspect Check
        if fig_width / fig_height < 0.8:
            fig_width = fig_height * 0.8
            
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        fig.patch.set_facecolor('#0f172a') 
        ax.axis('off')
        
        # Create table with MANUAL column widths
        table = ax.table(
            cellText=wrapped_data,
            colLabels=headers,
            colWidths=norm_widths,
            cellLoc='left',
            loc='center',
            colColours=['#1e293b'] * num_cols, 
            cellColours=[['#0f172a'] * num_cols for _ in range(num_rows)] 
        )

        # Styling cells
        table.auto_set_font_size(False)
        table.set_fontsize(base_font_size) 
        
        # Base height per line (normalized to figure)
        base_h = 0.9 / total_content_lines 

        for (row, col), cell in table.get_celld().items():
            cell.set_edgecolor('#334155')
            cell.set_linewidth(0.8)
            cell.set_text_props(horizontalalignment='left')
            
            if row >= 0:
                lines = row_line_counts[row] if row < len(row_line_counts) else 1
                cell.set_height(base_h * lines)

            if row == 0: # Header
                cell.set_text_props(weight='bold', color='#00d4ff', fontsize=header_font_size)
            else: # Normal cells
                cell.set_text_props(color='#cbd5e1', va='center')

        plt.title(title, pad=30, fontsize=20, fontweight='bold', color='#00d4ff', y=0.95)
        plt.tight_layout()

        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=140, bbox_inches='tight', facecolor='#0f172a')
        plt.close(fig)
        buf.seek(0)
        
        return buf.getvalue()
