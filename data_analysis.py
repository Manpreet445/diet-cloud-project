# Grabbing our Pandas tool and giving it a nickname 'pd' to save time typing
import pandas as pd

# 1. Load the dataset
df = pd.read_csv('All_Diets.csv')

# 2. Clean the data 
df.fillna(df.mean(numeric_only=True), inplace=True)

# 3. Print a sneak peek
print("Vibe check: Data loaded successfully!")
print(df.head())

# 4. Sort the Legos and find the average Protein, Carbs, and Fat for each Diet Type
avg_macros = df.groupby('Diet_type')[['Protein(g)', 'Carbs(g)', 'Fat(g)']].mean()

print("\n--- Average Macros by Diet Type ---")
print(avg_macros)

# 5. Make up our two brand new math scores (Ratios)
df['Protein_to_Carbs_ratio'] = df['Protein(g)'] / df['Carbs(g)']
df['Carbs_to_Fat_ratio'] = df['Carbs(g)'] / df['Fat(g)']

print("\n--- Sneak Peek at the New Scores ---")
print(df[['Recipe_name', 'Protein_to_Carbs_ratio', 'Carbs_to_Fat_ratio']].head())

# 6. Find the top 5 protein-rich recipes for each diet type
top_protein = df.sort_values('Protein(g)', ascending=False).groupby('Diet_type').head(5)

print("\n--- Top 5 High-Protein Recipes per Diet ---")
print(top_protein[['Diet_type', 'Recipe_name', 'Protein(g)']])

# 7. Find the diet type with the highest protein content overall
highest_protein_diet = avg_macros['Protein(g)'].idxmax()

print(f"\n--- The Ultimate Gym Bro Diet ---")
print(f"The diet with the highest average protein is: {highest_protein_diet.upper()}")

# 8. Identify the most common cuisines for each diet type
common_cuisines = df.groupby('Diet_type')['Cuisine_type'].agg(lambda x: x.mode()[0])

print("\n--- Most Common Cuisine for Each Diet ---")
print(common_cuisines)

# Grab our coloring book tools
import matplotlib.pyplot as plt
import seaborn as sns

# Setting a dark aesthetic vibe for the UI
sns.set_theme(style="darkgrid")

# --- VISUALIZATION 1: Bar Chart ---
print("\nLoading the Bar Chart... Close the picture window when you're done looking at it to continue!")

plt.figure(figsize=(10, 6))
sns.barplot(x=avg_macros.index, y=avg_macros['Protein(g)'], palette="viridis")

plt.title('Average Protein by Diet Type')
plt.ylabel('Average Protein (g)')
plt.xlabel('Diet Type')

plt.show()

# --- VISUALIZATION 2: The Heatmap ---
print("\nLoading the Heatmap... Close the picture window when you're done looking at it to continue!")

plt.figure(figsize=(10, 6))

sns.heatmap(avg_macros, annot=True, fmt=".1f", cmap="magma")

plt.title('Macronutrient Heatmap by Diet Type')
plt.ylabel('Diet Type')

plt.show()

# --- VISUALIZATION 3: The Scatter Plot ---
print("\nLoading the final boss... The Scatter Plot!")

plt.figure(figsize=(12, 7))

sns.scatterplot(data=top_protein, x='Cuisine_type', y='Protein(g)', hue='Diet_type', s=150, palette='Set2')

plt.title('Top 5 Protein-Rich Recipes: Distribution Across Cuisines')
plt.xlabel('Cuisine Type')
plt.ylabel('Protein (g)')

plt.xticks(rotation=45) 

plt.legend(title='Diet Type', bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()

plt.show()
print("\nTask 1 is officially 100% COMPLETE! Massive W.")