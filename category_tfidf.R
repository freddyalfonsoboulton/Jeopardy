library(tidytext)
library(data.table)
library(dplyr)
library(stringr)
library(tidyr)
library(ggplot2)

questions <- fread('jeopardy_questions.csv')
# binding question and answer together
questions[,full_text := paste(question_text, answer, sep = ' ')]
common_categories <- questions[,.(count = .N), by = category][order(count,decreasing = T)][2:11,category]


tidy_words <- questions %>% unnest_tokens(word, full_text)
tidy_words  <-  tidy_words  %>% count(category, word)
tidy_words <- tidy_words %>% bind_tf_idf(word,category, n)

tidy_words %>% filter(category %in% common_categories) %>% 
        group_by(category) %>% top_n(15) %>% ungroup() %>%
        ggplot(aes(word,tf_idf, fill = category)) + geom_col(show.legend = F) +
        facet_wrap(~ category, scales = 'free', nrow = 5, ncol = 2) +
        coord_flip() +
        labs(x = '', y = 'TF-IDF', 
             title = 'Highest TF-IDF Weights for Words in Most Common Jeopardy Categories') +
        theme(plot.title = element_text(hjust = 0.5)) +
        ggsave('jeopardy_tfid.png', height = 10, width = 8)
