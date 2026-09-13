package com.opsgenome.billing;

public class PaymentProcessor {
    public double computeTotal(Double amount) {
        
        if (amount == null) return 0.0;

        return amount.doubleValue() * 1.05;
    }
}
