library(tidytext)
library(data.table)
library(dplyr)
library(stringr)
library(tidyr)
library(ggplot2)

questions <- fread('jeopardy_questions.csv')

tidy_questions <- questions %>% unnest_tokens(word, question_text)
tidy_answers <- questions %>% unnest_tokens(word, answer)
tidy_answers <- tidy_answers %>% anti_join(stop_words) %>%
                mutate(round2 = ifelse(round == 'J', 'J', 'DJ'))

tidy_questions <- tidy_questions %>% anti_join(stop_words)
tidy_questions <- data.table(tidy_questions)
tidy_questions[,round2 := ifelse(round == 'J', 'J', 'DJ')]

#differences between words frequency across jeopardy rounds
frequency <- tidy_questions %>% count(round2, word) %>% group_by(round2) %>%
        mutate(proportion = n/sum(n)) %>% select(-n) %>%
        spread(round2, proportion)

frequency_answers <- tidy_answers %>% count(round2,word) %>% group_by(round2) %>%
        mutate(proportion = n/sum(n)) %>% select(-n) %>%
        spread(round2, proportion)

library(scales)
#Questions
ggplot(frequency, aes(x = J, y = DJ, color = abs(DJ - J))) +
        geom_jitter(alpha = 0.1, size = 0.5, width = 0.2, height = 0.2) + 
        geom_text(aes(label = word), vjust = 1.5, check_overlap = T, size =2.5) + 
        scale_x_log10(labels = percent_format()) +
        scale_y_log10(labels= percent_format()) + 
        labs(x = 'Jeopardy Round Proportion', y = 'Double Jeopary Proportion',
             title = 'Comparison of Question Word Frequencies between Jeopardy Rounds',
             subtitle = 'Final Jeopardy gets mapped to Double Jeopardy') + 
        geom_abline(intercept = 0, slope = 1, color = 'gray40') + 
        scale_color_gradient(low = "darkslategray4", high = "black") +
        theme(legend.position = 'none',
              plot.title = element_text(hjust = 0.5),
              plot.subtitle = element_text(hjust = 0.5))

#Answers 
ggplot(frequency_answers, aes(x = J, y = DJ, color = abs(DJ - J))) +
        geom_jitter(alpha = 0.1, size = 0.5, width = 0.2, height = 0.2) + 
        geom_text(aes(label = word), vjust = 1.5, check_overlap = T, size =2.5) + 
        scale_x_log10(labels = percent_format()) +
        scale_y_log10(labels= percent_format()) + 
        labs(x = 'Jeopardy Round Proportion', y = 'Double Jeopary Proportion',
             title = 'Comparison of Word Answer Frequencies between Jeopardy Rounds',
             subtitle = 'Final Jeopardy gets mapped to Double Jeopardy') + 
        geom_abline(intercept = 0, slope = 1, color = 'gray40') + 
        scale_color_gradient(low = "darkslategray4", high = "black") +
        theme(legend.position = 'none',
              plot.title = element_text(hjust = 0.5),
              plot.subtitle = element_text(hjust = 0.5))
        

