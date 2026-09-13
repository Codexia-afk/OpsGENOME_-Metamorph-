package com.opsgenome.billing;

public class PaymentProcessor {
    public double computeTotal(Double amount) {
        return amount.doubleValue() * 1.05;
    }
}
